import pys2let
import numpy as np
import healpy as hp
import os
from scipy import sparse

from pxmcmc.utils import expand_mlm, flatten_mlm, alm2map, map2alm, wavelet_basis
from pxmcmc.measurements import Identity, PathIntegral
from pxmcmc.transforms import WaveletTransform


class ForwardOperator:
    """
    Base Forward operator. Combines a transform and a measurement operator
    Children of this class must define analysis/synthesis forward and gradg functions
    Children must also take data and sig_d in the constructor
    """

    def __init__(self, data, sig_d, setting, transform=None, measurement=None):
        self.data = data
        self.sig_d = sig_d
        if setting not in ["analysis", "synthesis"]:
            raise ValueError
        self.setting = setting
        if transform is not None:
            self.transform = transform
        if measurement is not None:
            self.measurement = measurement

    def forward(self, X):
        if self.setting == "analysis":
            return self._forward_analysis(X)
        else:
            return self._forward_synthesis(X)

    def calc_gradg(self, preds):
        if self.setting == "analysis":
            return self._gradg_analysis(preds)
        else:
            return self._gradg_synthesis(preds)

    def _forward_analysis(self, X):
        return self.measurement.forward(X)

    def _forward_synthesis(self, X):
        realspace = self.transform.inverse(X)
        prediction = self.measurement.forward(realspace)
        return prediction

    def _gradg_analysis(self, preds):
        return self.measurement.adjoint(preds - self.data) / (self.sig_d ** 2)

    def _gradg_synthesis(self, preds):
        return self.transform.inverse_adjoint(self._gradg_analysis(preds))


class ISWTOperator(ForwardOperator):
    """
    Inverse spherical wavelet transfrom operator.
    Returns the spherical harmonic coefficients.
    Analysis: sample spherical harmonic coefficients
    Synthesis: sample harmonic wavelet coefficeints
    """

    def __init__(self, data, sig_d, L, B, J_min, setting, dirs=1, spin=0):
        super().__init__(data, sig_d, setting)

        self.nparams = L * L

        self.transform = WaveletTransform(L, B, J_min, dirs=dirs, spin=spin, out_type="harmonic")
        self.measurement = Identity(M=len(self.data), N=self.nparams)

    def _gradg_synthesis(self, preds):
        """
        Takes in predictions of harmonic coefficients and calculates gradients wrt scaling/wavelet coefficients
        """
        diff_lm = preds - self.data
        diff_lm_adj = self.measurement.adjoint(diff_lm)
        f = pys2let.alm2map_mw(diff_lm_adj, self.transform.L, self.transform.spin)
        f_wav_lm, f_scal_lm = self.transform.inverse_adjoint(f)
        return flatten_mlm(f_wav_lm, f_scal_lm) / (self.sig_d ** 2)


class SWC2PixOperator(ISWTOperator):
    """
    Inverse spherical wavelet transfrom operator.
    Returns pixel valyes.
    Analysis: sample pixel values
    Synthesis: sample harmonic wavelet coefficeints
    """

    def __init__(self, data, sig_d, Nside, L, B, J_min, setting, dirs=1, spin=0):
        super().__init__(data, sig_d, L, B, J_min, setting, dirs, spin)
        self.Nside = Nside

        if setting == "analysis":
            self.nparams = hp.nside2npix(Nside)

    def _forward_synthesis(self, X):
        clm = super()._forward_synthesis(X)
        clm_hp = pys2let.lm2lm_hp(clm, self.L)
        c = alm2map(clm_hp, self.Nside)
        return c

    def _forward_analysis(self, X):
        return X

    def _gradg_analysis(self, preds):
        return super()._gradg_analysis(preds)

    def _gradg_synthesis(self, preds):
        diff_hp = preds - self.data
        diff_lm_hp = map2alm(diff_hp, self.L)
        diff_lm_mw = pys2let.lm_hp2lm(diff_lm_hp, self.L)
        diff_mw = pys2let.alm2map_mw(diff_lm_mw, self.L, self.spin)

        f_wav, f_scal = pys2let.synthesis_adjoint_axisym_wav_mw(
            diff_mw, self.B, self.L, self.J_min
        )
        f_scal_lm = pys2let.map2alm_mw(f_scal, self.L, 0)
        f_wav_lm = np.zeros((self.L ** 2, self.nscales), dtype=np.complex)
        vlen = pys2let.mw_size(self.L)
        for j in range(self.nscales):
            f_wav_lm[:, j] = pys2let.map2alm_mw(
                f_wav[j * vlen : (j + 1) * vlen + 1], self.L, 0
            )
        return flatten_mlm(f_wav_lm, f_scal_lm) / (self.sig_d ** 2)


class GCPIntegralOperator(ForwardOperator):
    def __init__(
        self,
        datafile,
        Nside,
        L,
        B,
        J_min,
        setting,
        dirs=1,
        spin=0,
        path_matrix_file=None,
    ):
        self.Nside = Nside
        self.L = L
        self.B = B
        self.J_min = J_min
        self.J_max = pys2let.pys2let_j_max(self.B, self.L, self.J_min)
        self.nscales = self.J_max - self.J_min + 1
        self.dirs = dirs
        self.spin = spin

        if setting == "synthesis":
            basis = wavelet_basis(L, B, J_min, dirs, spin)
            self.nparams = np.prod(basis.shape)
        else:
            self.nparams = hp.nside2npix(Nside)

        self._read_datafile(datafile)
        self._get_path_matrix(path_matrix_file)

    def _read_datafile(self, datafile):
        """
        Expects a file with the following columns for each path:
        start_lat, start_lon, stop_lat, stop_lon, data, error
        Coordinates given in degrees
        TODO: Check what happens when each data point has a different error
        TODO: Figure out what to do with minor/major and nsim
        """
        all_data = np.loadtxt(datafile)
        start_lat = all_data[:, 0]
        start_lon = all_data[:, 1]
        self.start = np.stack([start_lat, start_lon], axis=1)
        stop_lat = all_data[:, 2]
        stop_lon = all_data[:, 3]
        self.stop = np.stack([stop_lat, stop_lon], axis=1)
        self.data = all_data[:, 4]
        sig_d = all_data[:, 5]
        self.sig_d = np.max(sig_d)

    def _get_path_matrix(self, path_matrix_file):
        if path_matrix_file is None:
            path_matrix_file = f"path_matrix_{self.Nside}.npz"
        if os.path.exists(path_matrix_file):
            self._read_path_matrix_file(path_matrix_file)
        else:
            self._build_path_matrix_file(path_matrix_file)

    def _read_path_matrix_file(self, path_martix_file):
        self.path_matrix = sparse.load_npz(path_martix_file)

    def _build_path_matrix_file(self, path_matrix_file):
        from greatcirclepaths import GreatCirclePath
        from multiprocessing import Pool

        def build_path(start, stop):
            path = GreatCirclePath(start, stop, self.Nside)
            path.get_points(1000)
            path.fill()
            return path.map

        itrbl = [(start, stop) for (start, stop) in zip(self.start, self.stop)]
        with Pool() as p:
            result = p.starmap_async(build_path, itrbl)
            paths = result.get()
        self.path_matrix = sparse.csr_matrix(paths)
        sparse.save_npz(path_matrix_file, self.path_matrix)
