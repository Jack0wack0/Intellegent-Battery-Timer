import dslogparser as dslp
import os

class DSConvertor:
    def __init__(self,dsLogDir=""):
        self.dsLogDir=dsLogDir
        self.destinationDr=""
        self.exclusionListFP=""

    def processDSLogs(self):
        for file in os.listdir(self.dsLogDir):
            fp=self.dsLogDir+"/"+file
            newDSLP=dslp.DSLogParser(fp)
            csvData=newDSLP.parse_data_v3()

    def addToExclusionList(self,fileName=""):
        with os.open() as f:
            f
