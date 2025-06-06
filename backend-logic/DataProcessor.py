import LinearRegression as lr
import CSVData as csvD
import numpy as np

class DataProcessor:
    def __init__(self,csvFile="",xColumnName="",yColumnName="",epochs=1000):
        self.data=csvD.CSVData(csvFile)
        xData=self.data.getColumnValues(xColumnName)
        yData=self.data.getColumnValues(yColumnName)
        learnRate=0.001
        bias=1

        self.lr=lr.LinearRegression(epochs,xData,yData,len(xData),learnRate,bias)
        self.lowestYValue=np.min(yData)


#BATTERY USEFUL INFO
#OVERALL DROP VOLTAGE
#SLOPE OF THE LINE
#VARIATION OFF LINE
#MATCH NUMBER
#BROWNOUTS
