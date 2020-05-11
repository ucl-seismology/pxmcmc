import pys2let
import numpy as np
from .utils import expand_mlm


class ForwardOperator:
    """
    Base Forward identity operator
    """

    def __init__(self, data, sig_d):
        self.data = data
        self.sig_d = sig_d
        self.nparams = len(data)

    def forward(self, X):
        return X

    def calc_gradg(self, preds):
        return (preds - self.data) / (self.sig_d ** 2)


class ISWTOperator(ForwardOperator):
    """
    Inverse spherical wavelet transfrom operator.
    Returns the spherical harmonic coefficients from the sampled harmonic wavelet coeffs
    """

    def __init__(self, data, sig_d, L, B, J_min, dirs=1, spin=0):
        super().__init__(data, sig_d)
        self.L = L
        self.B = B
        self.J_min = J_min
        self.J_max = pys2let.pys2let_j_max(self.B, self.L, self.J_min)
        self.nscales = self.J_max - self.J_min + 1

        phi_l, psi_lm = pys2let.wavelet_tiling(
            B, L + 1, dirs, spin, J_min
        )  # phi_l = 0, bug in pys2let?
        psi_lm = psi_lm[:, J_min:]
        phi_lm = np.zeros(((L + 1) ** 2, 1), dtype=np.complex)
        for ell in range(L + 1):
            phi_lm[ell * ell + ell] = phi_l[ell]
        self.basis = np.concatenate((phi_lm, psi_lm), axis=1)

        self.n_lm = self.basis.shape[0]
        self.nb = self.basis.shape[1]
        self.nparams = self.n_lm * self.nb

        self._calc_prefactors()

    def forward(self, X):
        """
        Forward modelling.  Takes a vector X containing the scaling and wavelet coefficients generated by the chain and predicts output real space map
        """
        wav_lm, scal_lm = expand_mlm(X, self.nscales)
        scal_lm_hp = pys2let.lm2lm_hp(scal_lm, self.L + 1)
        wav_lm_hp = np.zeros(
            [(self.L + 1) * (self.L + 2) // 2, self.nscales], dtype=np.complex,
        )
        for j in range(self.nscales):
            wav_lm_hp[:, j] = pys2let.lm2lm_hp(
                np.ascontiguousarray(wav_lm[:, j]), self.L + 1
            )
        clm_hp = pys2let.synthesis_axisym_lm_wav(
            wav_lm_hp, scal_lm_hp, self.B, self.L + 1, self.J_min
        )
        clm = pys2let.lm_hp2lm(clm_hp, self.L + 1)
        return clm

    def calc_gradg(self, preds):
        """
        Calculates the gradient of the data fidelity term, which should guide the MCMC search.
        """
        diff = np.concatenate([preds - self.data] * self.basis.shape[1])
        gradg = self.pf * diff / (self.sig_d ** 2)
        return gradg

    def _calc_prefactors(self):
        """
        Calculates prefactors of gradg which are constant throughout the chain, and so only need to be calculated once at the start.
        """
        prefactors = np.zeros(self.nparams, dtype=np.complex)
        for i, base in enumerate(self.basis.T):
            base_l0s = [base[l ** 2 + l] for l in range(self.L + 1)]
            for ell in range(self.L + 1):
                prefactors[
                    i * len(base) + ell ** 2 : i * len(base) + (ell + 1) ** 2
                ] = np.sqrt(4 * np.pi / (2 * ell + 1)) * base_l0s[ell]
        self.pf = prefactors
