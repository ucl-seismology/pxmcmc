import healpy as hp
import numpy as np
import pys2let

from pxmcmc.mcmc import PxMCMC, PxMCMCParams
from pxmcmc.forward import SWC2PixOperator
from pxmcmc.saving import save_mcmc

topo = hp.read_map("ETOPO1_Ice_hpx_256.fits", verbose=False)
sig_d = 0.03

L = 15
B = 1.5
J_min = 2
Nside = 32
topo_d = hp.ud_grade(topo, Nside)
forwardop = SWC2PixOperator(topo_d, sig_d, Nside, L, B, J_min)
params = PxMCMCParams(
    nsamples=int(5e5),
    nburn=0,
    ngap=0,
    complex=True,
    delta=1e-10,
    lmda=3e-8,
    mu=1e8,
    verbosity=1,
)

print(f"Number of data points: {len(topo_d)}")
print(f"Number of model parameters: {forwardop.nparams}")

mcmc = PxMCMC(forwardop, params)
mcmc.myula()

save_mcmc(
    mcmc,
    params,
    "/Volumes/Elements/PxMCMCoutputs/earthtopography",
    filename="myula",
    L=L,
    B=B,
    J_min=J_min,
    sig_d=sig_d,
    nparams=forwardop.nparams,
)