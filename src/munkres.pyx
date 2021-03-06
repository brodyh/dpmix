# Import the Python-level symbols of numpy
import numpy as np

# Import the C-level symbols of numpy
cimport numpy as np

cimport cython

# Numpy must be initialized. When using numpy from C or Cython you must
# _always_ do that, or you will have segfaults
np.import_array()


from libcpp.vector cimport vector
from libcpp cimport bool

cdef extern from "cpp/Munkres.h":
    cdef cppclass Munkres:
        Munkres()
        vector[vector[bool]] solve(vector[vector[double]] x)

   
def munkres(np.ndarray[np.double_t,ndim=2] A):
    '''
    calculate the minimum cost assigment of a cost matrix (must be numpy.double type)
    '''
    cdef int x = A.shape[0]
    cdef int y = A.shape[1]
    cdef Munkres* munk = new Munkres()
    cdef np.ndarray rslt = np.zeros([x, y], dtype=np.bool)
    cdef vector[vector[double]] cost
    for i in range(x):
        cost.push_back(vector[double]())
        for j in range(y):
            cost[i].push_back(A[i,j])
        
    cdef vector[vector[bool]] ans = munk.solve(cost)
    
    for i in range(x):
        for j in range(y):
            rslt[i,j] = ans[i][j]
    return rslt

@cython.boundscheck(False)
def _get_cost(np.ndarray[int, ndim=1] x, np.ndarray[int, ndim=1] y, np.ndarray[np.double_t, ndim=2] C):
    cdef int n = x.shape[0]
    # shut off bounds check
    cdef int ii = 0
    cdef int jj = 0
    for i in range(n):
        ii = x[i]
        jj = y[i]
        C[ii, jj] -= 1.0 
    return


    