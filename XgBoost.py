import xgboost as xgb
import quadratic_weighted_kappa
import numpy as np

class XGBoostModel:
    
    def __init__(self, num_rounds, max_depth, eta, colsample_bytree, objective,  silent=True):
        self.param = {'max_depth':max_depth, 'eta': eta, 'silent':1, 'min_child_weight':3, 'subsample' : 0.7 ,"early_stopping_rounds":10, 
            'objective': objective, 'colsample_bytree': colsample_bytree, "silent" : silent}
     #   self.learning_rates = learning_rates
        self.num_round=num_rounds

    #def __init__(self, eta, l, alpha, rounds):
     #   self.param = {'objective': 'reg:linear'}
#, 'num_class': 8}
     #   self.param['booster'] = 'gblinear' # gbtree has more params to tune...
      #  self.param['eta'] = eta
       # self.param['lambda'] = l
        #self.param['alpha'] = alpha       
        #self.num_round=rounds
    
        
    def fit(self, xTrain, yTrain):
        dtrain = xgb.DMatrix(xTrain,label=yTrain)
        watchlist  = [(dtrain,'train')]
        self.bst = xgb.train(self.param, dtrain, self.num_round, watchlist)
#, obj=softkappaobj, feval=evalerror)
        
    def predict(self, testData):
        dTest = xgb.DMatrix(testData)
        return self.bst.predict(dTest)
    #    preds = softmax(self.bst.predict(dTest))
     #   return np.argmax(preds, axis=1) + 1

def softmax(score):
    score = np.asarray(score, dtype=float)
    score = np.exp(score-np.max(score))
   # print "SHAPE IS %s" % score.shape
    score /= np.sum(score, axis=1)[:,np.newaxis]
    return score

## soft version of kappa score using the class probability
## inspired by @George Mohler in the Higgs competition
## https://www.kaggle.com/c/higgs-boson/forums/t/10286/customize-loss-function-in-xgboost/53459#post53459
## NOTE: As also discussed in the above link, it is hard to tune the hessian to get it to work.
def softkappaobj(preds, dtrain):
    ## label are in [0,1,2,3] as required by XGBoost for multi-classification
    labels = dtrain.get_label() + 1
    labels = np.asarray(labels, dtype=int)
    preds = softmax(preds)
    M = preds.shape[0]
    N = preds.shape[1]

    ## compute O (enumerator)
    O = 0.0
    for j in range(N):
        wj = (labels - (j+1.))**2
        O += np.sum(wj * preds[:,j])
    
    ## compute E (denominator)
    hist_label = np.bincount(labels)[1:]
    hist_pred = np.sum(preds, axis=0)
    E = 0.0
    for i in range(N):
        for j in range(N):
            E += pow(i - j, 2.0) * hist_label[i] * hist_pred[j]

    ## compute gradient and hessian
    grad = np.zeros((M, N))
    hess = np.zeros((M, N))
    for n in range(N):
        ## first-order derivative: dO / dy_mn
        dO = np.zeros((M))
        for j in range(N):
            indicator = float(n == j)
            dO += ((labels - (j+1.))**2) * preds[:,n] * (indicator - preds[:,j])
        ## first-order derivative: dE / dy_mn
        dE = np.zeros((M))
        for k in range(N):
            for l in range(N):
                indicator = float(n == k)
                dE += pow(k-l, 2.0) * hist_label[l] * preds[:,n] * (indicator - preds[:,k])
        ## the grad
        grad[:,n] = -M * (dO * E - O * dE) / (E**2)
        
        ## second-order derivative: d^2O / d (y_mn)^2
        d2O = np.zeros((M))
        for j in range(N):
            indicator = float(n == j)
            d2O += ((labels - (j+1.))**2) * preds[:,n] * (1 - 2.*preds[:,n]) * (indicator - preds[:,j])
       
        ## second-order derivative: d^2E / d (y_mn)^2
        d2E = np.zeros((M))
        for k in range(N):
            for l in range(N):
                indicator = float(n == k)
                d2E += pow(k-l, 2.0) * hist_label[l] * preds[:,n] * (1 - 2.*preds[:,n]) * (indicator - preds[:,k])
        ## the hess
        hess[:,n] = -M * ((d2O * E - O * d2E)*(E**2) - (dO * E - O * dE) * 2. * E * dE) / (E**4)

    grad *= -1.
    hess *= -1.
    # this pure hess doesn't work in my case, but the following works ok
    # use a const
    #hess = 0.000125 * np.ones(grad.shape, dtype=float)
    # or use the following...
    scale = 0.000125 / np.mean(abs(hess))
    hess *= scale
    hess = np.abs(hess) # It works!! no idea...
    grad.shape = (M*N)
    hess.shape = (M*N)
    return grad, hess

# evalerror is your customized evaluation function to 
# 1) decode the class probability 
# 2) compute quadratic weighted kappa
def evalerror(preds, dtrain):
    ## label are in [0,1,2,3] as required by XGBoost for multi-classification
    labels = dtrain.get_label() + 1
    ## class probability
    preds = softmax(preds)
    ## decoding (naive argmax decoding)
    pred_labels = np.argmax(preds, axis=1) + 1
    ## compute quadratic weighted kappa (using implementation from @Ben Hamner
    ## https://github.com/benhamner/Metrics/blob/master/Python/ml_metrics/quadratic_weighted_kappa.py
    kappa = quadratic_weighted_kappa.quadratic_weighted_kappa(labels, pred_labels)
    return 'kappa',  kappa
