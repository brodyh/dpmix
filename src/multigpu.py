"""
Support for multi-GPU via threading for dpmix MCMC
Written by: Andrew Cron
"""

from mpi4py import MPI
import numpy as np
import sys; import os
from utils import BEM_Task, MCMC_Task, Init_Task

########### Multi GPU ##########################
_datadevmap = {}
_dataind = {}

def init_GPUWorkers(data, devslist=None):

    worker_file = os.path.dirname(__file__) + os.sep + 'gpuworker.py'
    ndev = len(devslist)

    workers = MPI.COMM_SELF.Spawn(sys.executable, args=[worker_file], maxprocs = ndev)
    ## dpmix and BEM
    if type(data) == np.ndarray:
        nobs, ndim = data.shape
        lenpart = nobs / len(devslist)
        partitions = range(0, nobs, lenpart); 
        if len(partitions)==len(devslist):
            partitions.append(nobs)
        else:
            partitions[-1] = nobs
    
        #launch threads
        for i in xrange(ndev):
            todat = np.asarray(data[partitions[i]:partitions[i+1]], dtype='d')
            task = np.array(0, dtype='i')
            #task = Init_Task(todat.shape[0], todat.shape[1], int(devslist[i]))
            workers.Isend([task, MPI.INT], dest=i, tag=11)
            #print 'sent task'
            params = np.array([todat.shape[0], todat.shape[1], int(devslist[i])], dtype='i')
            workers.Send([params, MPI.INT], dest=i, tag=12)
            #print 'params'
            workers.Send([todat, MPI.DOUBLE], dest=i, tag=13)
            #print 'data now waiting'
            workers.Recv([task, MPI.INT], source=i, tag=14)
            #print 'made it'

            i+=1
    else: ## HDP .. one or more datasets per GPU
        ndata = len(data)
        for i in xrange(ndata):
            dev = int(devslist[i%len(devslist)])
            thd = i%len(devslist)
            todat = np.asarray(data[i], dtype='d')
            task = np.array(0, dtype='i')
            workers.Isend([task, MPI.INT], dest=thd, tag=11)
            params = np.array([todat.shape[0], todat.shape[1], dev], dtype='i')
            workers.Send([params, MPI.INT], dest=thd, tag=12)
            #task = Init_Task(todat.shape[0], todat.shape[1], dev)
            #workers.isend(task, dest=thd, tag=11)
            workers.Send([todat, MPI.DOUBLE], dest=thd, tag=13)
            dind = np.array(0, dtype='i')
            workers.Recv([dind, MPI.INT], source=thd, tag=14)
            _dataind[i] = dind
            _datadevmap[i] = thd
    #print 'initialized!'
    return workers

def get_hdp_labels_GPU(workers, w, mu, Sigma, relabel=False):

    #import pdb; pdb.set_trace()
    ndev = workers.remote_group.size
    ndata = len(_datadevmap)

    tasks = []
    for _i in xrange(ndev): tasks.append([])
    labels = []; Z = [];
    for _i in xrange(ndata): labels.append(None); Z.append(None)

    ## setup task
    for i in xrange(ndata):
        tasks[_datadevmap[i]].append(MCMC_Task(Sigma.shape[0], relabel, _dataind[i], i))

    for i in xrange(ndev):
        # send the number of tasks
        tsk = np.array(1, dtype='i'); 
        workers.Isend([tsk, MPI.INT], dest=i, tag=11)
        numtasks = np.array(len(tasks[i]), dtype='i')
        workers.Send([numtasks,MPI.INT], dest=i, tag=12)

        for tsk in tasks[i]:
            
            params = np.array([tsk.dataind, tsk.ncomp, int(tsk.relabel)+1, tsk.gid], dtype='i')
            workers.Send([params, MPI.INT], dest=i, tag=13)

            workers.Send([np.asarray(w[tsk.gid].copy(),dtype='d'), MPI.DOUBLE], dest=i, tag=21)
            workers.Send([np.asarray(mu, dtype='d'), MPI.DOUBLE], dest=i, tag=22)
            workers.Send([np.asarray(Sigma, dtype='d'), MPI.DOUBLE], dest=i, tag=23)

    for i in xrange(ndev):
        numres = np.array(0, dtype='i'); workers.Recv([numres,MPI.INT], source=i, tag=13)
        #print numres
        #results = workers.recv(source=i, tag=13)
        for it in range(numres):
            rnobs = np.array(0, dtype='i'); workers.Recv([rnobs,MPI.INT], source=i, tag=21)
            labs = np.empty(rnobs, dtype='i')
            workers.Recv([labs, MPI.INT], source=i, tag=22)
            rgid = np.array(0, dtype='i'); workers.Recv([rgid,MPI.INT], source=i, tag=23)
            labels[rgid] = labs
            if relabel:
                cZ = np.empty(rnobs, dtype='i')
                workers.Recv([cZ, MPI.INT], source=i, tag=24)
                Z[rgid] = cZ


    return labels, Z 

def get_labelsGPU(workers, w, mu, Sigma, relabel=False):
    # run all the threads
    ndev = workers.remote_group.size
    nobs, i = 0, 0
    partitions = [0]

    for i in xrange(ndev):
        # give new params
        task = np.array(1, dtype='i')
        workers.Isend([task,MPI.INT], dest=i, tag=11)
        numtasks = np.array(1, dtype='i')
        workers.Send([numtasks,MPI.INT], dest=i, tag=12)
        params = np.array([0, len(w), int(relabel)+1, 1], dtype='i')
        workers.Send([params,MPI.INT], dest=i, tag=13)

        # give bigger params
        workers.Send([np.asarray(w,dtype='d'), MPI.DOUBLE], dest=i, tag=21)
        workers.Send([np.asarray(mu,dtype='d'), MPI.DOUBLE], dest=i, tag=22)
        workers.Send([np.asarray(Sigma,dtype='d'), MPI.DOUBLE], dest=i, tag=23)
    #gather the results

    labs=[]; Zs=[];
    for i in xrange(ndev):
        numres = np.array(0, dtype='i'); workers.Recv(numres, source=i, tag=13)
        rnobs = np.array(0, dtype='i'); workers.Recv(rnobs, source=i, tag=21)

        nobs += rnobs
        partitions.append(nobs)
        lab = np.empty(rnobs, dtype='i')
        workers.Recv([lab, MPI.INT], source=i, tag=22)
        labs.append(lab)
        gid = np.array(0, dtype='i'); workers.Recv([gid, MPI.INT], tag=23)
        if relabel:
            Z = np.empty(rnobs, dtype='i')
            workers.Recv([Z, MPI.INT], source=i, tag=24)
            Zs.append(Z)


    res = np.zeros(nobs, dtype='i')
    if relabel:
        Z = res.copy()
    else:
        Z = None

    for i in xrange(ndev):
        res[partitions[i]:partitions[i+1]] = labs[i]
        if relabel:
            Z[partitions[i]:partitions[i+1]] = Zs[i]

    return res, Z

def get_expected_labels_GPU(workers, w, mu, Sigma):
    # run all the threads
    ndev = workers.remote_group.size
    ncomp = len(w)
    ndim = Sigma.shape[1]
    nobs, i = 0, 0
    partitions = [0]

    for i in xrange(ndev):
        # give new params
        task = np.array(1, dtype='i')
        workers.Isend([task,MPI.INT], dest=i, tag=11)
        numtasks = np.array(1, dtype='i')
        workers.Send([numtasks,MPI.INT], dest=i, tag=12)
        params = np.array([0, len(w), 0], dtype='i')
        workers.Send([params,MPI.INT], dest=i, tag=13)

        # give bigger params
        workers.Send([np.asarray(w,dtype='d'), MPI.DOUBLE], dest=i, tag=21)
        workers.Send([np.asarray(mu,dtype='d'), MPI.DOUBLE], dest=i, tag=22)
        workers.Send([np.asarray(Sigma,dtype='d'), MPI.DOUBLE], dest=i, tag=23)

    #gather results
    xbars = []; densities=[]; cts = []
    ll = 0

    for i in xrange(ndev):
        numres = np.array(0, dtype='i'); workers.Recv(numres, source=i, tag=13)
        rnobs = np.array(0, dtype='i'); workers.Recv(rnobs, source=i, tag=21)

        nobs += rnobs
        partitions.append(nobs)
        ct = np.empty(ncomp, dtype='d')
        workers.Recv([ct, MPI.DOUBLE], source=i, tag=22)
        cts.append(ct)
        xbar = np.empty(ncomp*ndim, dtype='d')
        workers.Recv([xbar, MPI.DOUBLE], source=i, tag=23)
        xbars.append(xbar.reshape(ncomp, ndim))
        dens = np.empty(rnobs*ncomp, dtype='d')
        workers.Recv([dens, MPI.DOUBLE], source=i, tag=24)
        densities.append(dens.reshape(rnobs, ncomp))
        nll = np.array(0, dtype='d'); workers.Recv([nll, MPI.DOUBLE], source=i, tag=25)
        ll += nll
        gid = np.array(0, dtype='i'); workers.Recv([gid, MPI.INT], tag=26)

    dens = np.zeros((nobs, ncomp), dtype='d')
    xbar = np.zeros((ncomp, ndim), dtype='d')
    ct = np.zeros(ncomp, dtype='d')
    #import pdb; pdb.set_trace()
    for i in xrange(ndev):
        ct += cts[i]
        xbar += xbars[i]
        dens[partitions[i]:partitions[i+1], :] = densities[i]
        
    return ll, ct, xbar, dens

def kill_GPUWorkers(workers):
    #poison pill to each child 
    ndev = workers.remote_group.size
    msg = np.array(-1, dtype='i')
    for i in xrange(ndev):
        workers.Isend([msg,MPI.INT], dest=i, tag=11)
    workers.Disconnect()

    
        


