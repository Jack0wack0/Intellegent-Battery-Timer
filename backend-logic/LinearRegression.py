import numpy as np
import matplotlib.pyplot as plt

class _LinearRegressionMath:
        #Sum Squared Error Function
    def SSE(y,pred):
        return 0.5*np.sum((y-pred)**2)

        #Returns the Derivative of a Weight
    def GetWeightDerivative(y,pred,x):
        return np.sum(-(y-pred)*x)

        #Returns the Last Output
        #Using Weight1, Weight0, Bias, and the Input
    def GetLastOutput(w0,x0,w1,x1):
        return w0*x0+w1*x1

        #Returns the Standard Deviation of the Input
    def StandardDeviation(data,mean):
        summation=np.sum((mean-data)**2)
        return (summation/len(data))**0.5
    
        #Returns a normalized set of data
        #Set of data within a range of 0-1 that contains the same variation as the previous values
    def Normalize(data):
        min=np.amin(data)
        range=np.amax(data)-min
        return np.array((data-min)/range)
    
        #Gets the variation of each value off the line of best fit
    def GetPointVariation(y,pred):
        variation=np.array(y-pred)
        return variation

        

class LinearRegression:
    """
        Instantiates a new linear regression model. Linear regression is used to find the line of best fit,
        which is used to find and visualize a correlation between an independent and dependent variable.

        Params
        -------------------------------------------------------------------------------
        - epochs: The number of iterations the model will run through.
        
        - xValues: The dependent variable used on the x-axis.

        - yValues: The independent variable used on the y-axis.

        - size: The desired number of values from the x and yValue arrays.

        - learningRate: The rate at which the model tries to go to the desired error. (If the number is too low it will take a long time, if it is to high it will overshoot and oscillate)
    
        - bias: Can be used to change the desired slope of the line.
        -------------------------------------------------------------------------------

        Funcs
        -------------------------------------------------------------------------------
        - train: Runs the model for the desired epochs and prints the derivatives, the weights, and the current epoch to the terminal.

        - plot: Plots the line of best fit and shows variation off the line
        -------------------------------------------------------------------------------
    """
    def __init__(self,epochs,xValues,yValues,size,learnRate=0.001,bias=1):
        lrMath=_LinearRegressionMath
        #Bias
        self.x0=bias
        #Weights (Randomly Assign Starting Weights)
        self.w0=np.random.uniform(-2,1,size=1)
        self.w1=np.random.uniform(2,3,size=1)
        #x-values
        self.xVals=np.array(xValues[0:size])
        #y-values
        self.yVals=np.array(yValues[0:size])
        #Normalized x-values
        self.x1=lrMath.Normalize(self.xVals)
        #Normalized y-values
        self.y=lrMath.Normalize(self.yVals)
        #Learning rate
        self.learnRate=learnRate
        #Epochs
        self.epochs=epochs

    def train(self):
        lrMath=_LinearRegressionMath
        
        for epoch in range(self.epochs):
                pred=lrMath.GetLastOutput(self.w0,self.x0,self.w1,self.x1)
                error=lrMath.SSE(self.y,pred)
                derivw0=lrMath.GetWeightDerivative(self.y,pred,self.x0)
                derivw1=lrMath.GetWeightDerivative(self.y,pred,self.x1)
                self.w0=self.w0-self.learnRate*derivw0
                self.w1=self.w1-self.learnRate*derivw1
                print(f"Deriv0: {derivw0} Deriv1: {derivw1}")
                print(f"w0: {self.w0} w1: {self.w1}")
                print(f"Current Epoch: {epoch} Error: {error}")
        
    def plot(self,title,xlabel,ylabel,tickNames=[]):
        lrMath=_LinearRegressionMath

        lrPred=lrMath.GetLastOutput(self.w0,self.x0,self.w1,self.x1)
        dif=lrMath.GetPointVariation(self.y,lrPred)
        plt.scatter(self.x1,self.y)
        plt.plot(self.x1,lrPred)
        plt.plot(self.x1,dif)
        plt.title(title)
        plt.xlabel(xlabel)
        plt.ylabel(ylabel)
        plt.xticks(self.x1,tickNames,rotation="vertical")
        plt.show()
                