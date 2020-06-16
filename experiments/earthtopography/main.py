import healpy as hp
import datetime

from pxmcmc.mcmc import MYULA, PxMALA, PxMCMCParams
from pxmcmc.forward import SWC2PixOperator
from pxmcmc.prox import L1
from pxmcmc.saving import save_mcmc

topo = hp.read_map("ETOPO1_Ice_hpx_256.fits", verbose=False)
sig_d = 0.03

L = 16
B = 1.5
J_min = 2
Nside = 32
setting = "synthesis"
topo_d = hp.ud_grade(topo, Nside)
forwardop = SWC2PixOperator(topo_d, sig_d, Nside, L, B, J_min, setting)
params = PxMCMCParams(
    nsamples=int(1e3),
    nburn=0,
    ngap=10,
    complex=True,
    delta=2.5e-8,
    lmda=1e-7,
    mu=1,
    verbosity=100,
)
regulariser = L1(setting, None, None, params.lmda * params.mu)

print(f"Number of data points: {len(topo_d)}")
print(f"Number of model parameters: {forwardop.nparams}")

NOW = datetime.datetime.now()

mcmc = PxMALA(forwardop, regulariser, params)
mcmc.run()

save_mcmc(
    mcmc,
    params,
    ".",
    filename=f"pxmala_{NOW.strftime('%d%m%y_%H%M%S')}",
    L=L,
    B=B,
    J_min=J_min,
    sig_d=sig_d,
    nparams=forwardop.nparams,
)
