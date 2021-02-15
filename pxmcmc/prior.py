import numpy as np
import pys2let
import pyssht

from pxmcmc.utils import soft, mw_map_weights


class L1:
    """
    L1-norm regulariser
    """

    def __init__(self, setting, fwd, adj, T):
        """
        setting = "analysis" or "synthesis"
        fwd = function handle for forward transform operator
        adj = function handle for adjoint transform operator
        T = threshold for soft thresholding
        """
        assert setting in ["analysis", "synthesis"]
        self.setting = setting
        self.fwd = fwd
        self.adj = adj
        self.T = T

    def prior(self, X):
        return sum(abs(X))

    def proxf(self, X):
        if self.setting == "synthesis":
            return self._proxf_synthesis(X)
        else:
            return self._proxf_analysis(X)

    def _proxf_synthesis(self, X):
        return soft(X, self.T)

    def _proxf_analysis(self, X):
        return X + self.fwd(soft(self.adj(X), self.T) - self.adj(X))


class S2_Wavelets_L1(L1):
    """
    L1 regulariser for wavelets on S2 (MW sampling)
    Performs some weighting to avoid overemphasizing pixels at the poles
    """

    def __init__(self, setting, fwd, adj, T, L, B, J_min, dirs=1, spin=0):
        super().__init__(setting, fwd, adj, T)
        self.L = L
        self.B = B
        self.J_min = J_min
        self.J_max = pys2let.pys2let_j_max(B, L, J_min)
        self.nscales = self.J_max - J_min + 1
        self.dirs = dirs
        self.spin = spin
        self.map_size = pyssht.sample_length(L, Method="MW")
        if setting == "synthesis":
            bls = self._get_bandlimits()
            self.map_weights = np.concatenate(
                [mw_map_weights(l) for l in bls]
            )
        else:
            self.map_weights = mw_map_weights(L)
        self.T *= self.map_weights ** 2

    def prior(self, X):
        return super().prior(self.map_weights * X)

    def _proxf_synthesis(self, X):
        WX = self.map_weights * X
        return X + (1 / self.map_weights) * (soft(WX, self.T) - WX)

    def _proxf_analysis(self, X):
        raise NotImplementedError

    def _get_bandlimits(self):
        phi_l, psi_lm = pys2let.wavelet_tiling(
            self.B, self.L, self.dirs, self.J_min, self.spin
        )
        psi_l = np.zeros((psi_lm.shape[1], self.L))
        for j, psi in enumerate(psi_lm.T):
            psi_l[j, :] = np.array([psi[l ** 2 + l] for l in range(self.L)])
        gamma_l = np.vstack([phi_l, psi_l])
        bandlimits = np.zeros(gamma_l.shape[0], dtype=int)
        for j, gamma in enumerate(gamma_l):
            pass
            bandlimits[j] = np.nonzero(gamma)[0].max() + 1
        return bandlimits
