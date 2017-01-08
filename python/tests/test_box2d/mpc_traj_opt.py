import os
import os.path
import sys
import numpy as np
import scipy as sp
from copy import deepcopy
from scipy.stats import multivariate_normal
from numpy.linalg import LinAlgError


class MpcTrajOpt(object):
    def __init__(self, M):
        self.M = M
        
    def runmpc(self, X_t, traj_distr, traj_info, cur_t):
        dU = traj_distr.dU
        dX = traj_distr.dX
        trajinfo = deepcopy(traj_info)
        trajinfo.x0mu = X_t
        trajinfo.x0sigma = np.zeros([dX, dX])
        
        mu, sigma = self.forward(traj_distr, trajinfo, cur_t)
        new_traj_distr = self.backward(traj_distr, trajinfo, X_t, mu, sigma, cur_t)
        
        return new_traj_distr, mu, sigma
        
    def forward(self, traj_distr, traj_info, cur_t):
        """
        Perform LQR forward pass. Computes state-action marginals from
        dynamics and policy.
        Args:
            traj_distr: A linear Gaussian policy object.
            traj_info: A TrajectoryInfo object.
        Returns:
            mu: A T x dX mean action vector.
            sigma: A T x dX x dX covariance matrix.
        """
        # Compute state-action marginals from specified conditional
        # parameters and current traj_info.
        T = self.M
        dU = traj_distr.dU
        dX = traj_distr.dX
    
        # Constants.
        idx_x = slice(dX)
    
        # Allocate space.
        sigma = np.zeros((T, dX+dU, dX+dU))
        mu = np.zeros((T, dX+dU))
    
        # Pull out dynamics.
        Fm = traj_info.dynamics.Fm
        fv = traj_info.dynamics.fv
        dyn_covar = traj_info.dynamics.dyn_covar
    
        # Set initial covariance (initial mu is always zero).
        sigma[0, idx_x, idx_x] = traj_info.x0sigma
        mu[0, idx_x] = traj_info.x0mu
    
        for t in range(T):
            t_traj = cur_t+t
            sigma[t, :, :] = np.vstack([
                np.hstack([
                    sigma[t, idx_x, idx_x],
                    sigma[t, idx_x, idx_x].dot(traj_distr.K[t_traj, :, :].T)
                ]),
                np.hstack([
                    traj_distr.K[t_traj, :, :].dot(sigma[t, idx_x, idx_x]),
                    traj_distr.K[t_traj, :, :].dot(sigma[t, idx_x, idx_x]).dot(
                        traj_distr.K[t_traj, :, :].T
                    ) + traj_distr.pol_covar[t_traj, :, :]
                ])
            ])
            mu[t, :] = np.hstack([
                mu[t, idx_x],
                traj_distr.K[t_traj, :, :].dot(mu[t, idx_x]) + traj_distr.k[t_traj, :]
            ])
            if t < T - 1:
                sigma[t+1, idx_x, idx_x] = \
                        Fm[t_traj, :, :].dot(sigma[t, :, :]).dot(Fm[t_traj, :, :].T) + \
                        dyn_covar[t_traj, :, :]
                mu[t+1, idx_x] = Fm[t_traj, :, :].dot(mu[t, :]) + fv[t_traj, :]
        return mu, sigma
    
    def backward(self, prev_traj_distr, traj_info, x0, mu, sigma, cur_t):
        """
        Perform LQR backward pass. This computes a new linear Gaussian
        policy object.
        Args:
            prev_traj_distr: A linear Gaussian policy object from
                previous iteration.
            traj_info: A TrajectoryInfo object.
            eta: Dual variable.
            algorithm: Algorithm object needed to compute costs.
            m: Condition number.
        Returns:
            traj_distr: A new linear Gaussian policy.
            new_eta: The updated dual variable. Updates happen if the
                Q-function is not PD.
        """
        # Constants.
        T = self.M
        dU = prev_traj_distr.dU
        dX = prev_traj_distr.dX

        # TODO: Change size to M
        traj_distr = prev_traj_distr.nans_like()
        #traj_distr.T = self.M
        
        """
        # TODO: Check BADMM need this?
        # Store pol_wt if necessary
        if type(algorithm) == AlgorithmBADMM:
            pol_wt = algorithm.cur[m].pol_info.pol_wt
        """

        idx_x = slice(dX)
        idx_u = slice(dX, dX+dU)

        # Pull out dynamics.
        Fm = traj_info.dynamics.Fm
        fv = traj_info.dynamics.fv

        # Non-SPD correction terms.
        eta = 0
        del_ = 1e-4#self._hyperparams['del0']
        eta0 = eta

        # Run dynamic programming.
        fail = True
        while fail:
            fail = False  # Flip to true on non-symmetric PD.

            # Allocate.
            Vxx = np.zeros((T, dX, dX))
            Vx = np.zeros((T, dX))

            fCm, fcv = self.compute_costs(x0, mu, sigma, dX, dU)

            # Compute state-action-state function at each time step.
            for t in range(T - 1, -1, -1):
                t_traj = cur_t+t
                # Add in the cost.
                Qtt = fCm[t, :, :]  # (X+U) x (X+U)
                Qt = fcv[t, :]  # (X+U) x 1

                # Add in the value function from the next time step.
                if t < T - 1:
                    """
                    # TODO: Check BADMM need this?
                    if type(algorithm) == AlgorithmBADMM:
                        multiplier = (pol_wt[t+1] + eta)/(pol_wt[t] + eta)
                    else:
                        multiplier = 1.0
                    """
                    multiplier = 1.0
                    Qtt = Qtt + multiplier * \
                            Fm[t_traj, :, :].T.dot(Vxx[t+1, :, :]).dot(Fm[t_traj, :, :])
                    Qt = Qt + multiplier * \
                            Fm[t_traj, :, :].T.dot(Vx[t+1, :] +
                                            Vxx[t+1, :, :].dot(fv[t_traj, :]))

                # Symmetrize quadratic component.
                Qtt = 0.5 * (Qtt + Qtt.T)
                Qtt[idx_u, idx_u] += eta*np.eye(dU)
                
                # Compute Cholesky decomposition of Q function action
                # component.
                try:
                    U = sp.linalg.cholesky(Qtt[idx_u, idx_u])
                    L = U.T
                except LinAlgError as e:
                    # Error thrown when Qtt[idx_u, idx_u] is not
                    # symmetric positive definite.
                    #LOGGER.debug('MPC LinAlgError: %s', e)
                    fail = True
                    break

                # Store conditional covariance, inverse, and Cholesky.
                traj_distr.inv_pol_covar[t, :, :] = Qtt[idx_u, idx_u]
                traj_distr.pol_covar[t, :, :] = sp.linalg.solve_triangular(
                    U, sp.linalg.solve_triangular(L, np.eye(dU), lower=True)
                )
                traj_distr.chol_pol_covar[t, :, :] = sp.linalg.cholesky(
                    traj_distr.pol_covar[t, :, :]
                )

                # Compute mean terms.
                traj_distr.k[t, :] = -sp.linalg.solve_triangular(
                    U, sp.linalg.solve_triangular(L, Qt[idx_u], lower=True)
                )
                traj_distr.K[t, :, :] = -sp.linalg.solve_triangular(
                    U, sp.linalg.solve_triangular(L, Qtt[idx_u, idx_x],
                                                  lower=True)
                )

                # Compute value function.
                Vxx[t, :, :] = Qtt[idx_x, idx_x] + \
                        Qtt[idx_x, idx_u].dot(traj_distr.K[t, :, :])
                Vx[t, :] = Qt[idx_x] + Qtt[idx_x, idx_u].dot(traj_distr.k[t, :])
                Vxx[t, :, :] = 0.5 * (Vxx[t, :, :] + Vxx[t, :, :].T)

            # Increment eta on non-SPD Q-function.
            if fail:
                #"""
                old_eta = eta
                eta = eta0 + del_
                #LOGGER.debug('Increasing eta: %f -> %f', old_eta, eta)
                print 'Increasing eta: %f -> %f', old_eta, eta
                del_ *= 2  # Increase del_ exponentially on failure.
                if eta >= 1e16:
                    if np.any(np.isnan(Fm)) or np.any(np.isnan(fv)):
                        raise ValueError('NaNs encountered in dynamics!')
                    raise ValueError('Failed to find PD solution even for very \
                            large eta (check that dynamics and cost are \
                            reasonably well conditioned)!')
                #"""
        return traj_distr
    
    def compute_costs(self, x0, mu, sigma, dX, dU):
        fCm = np.zeros([self.M, dX+dU, dX+dU])
        fcv = np.zeros([self.M, dX+dU])
        
        idx_x = slice(dX)
        idx_u = slice(dX, dX+dU)
        
        # Cost = -logp(x_t'|x_t)
        # Gradient = inv(Sigma)*(x0 - mu)
        # Hessian = inv(Sigma)
        for t in range(self.M - 1, 0, -1):
            inv_sigma = np.linalg.inv(sigma[t,idx_x,idx_x])
            fcv[t, idx_x] = inv_sigma.dot(x0 - mu[t,idx_x]) # Gradient
            fCm[t, idx_x, idx_x] = inv_sigma # Hessian
        
        return fCm, fcv