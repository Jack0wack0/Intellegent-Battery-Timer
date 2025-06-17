import dslogparser as dslp
from pathlib import Path
import pathlib
import os

class DSConvertor:
    def __init__(self,dsLogDir=""):
        self.dsLogDir=dsLogDir
        self.destinationDr=os.path.join(os.path.dirname(os.path.realpath(__file__)),"csvDSLogs")
        self.exclusionListFP=os.path.join(os.path.dirname(os.path.realpath(__file__)),"exclusionListFP.txt")

    def processDSLogs(self):
        for file in os.listdir(self.dsLogDir)[0:2]:
            with Path.open(self.exclusionListFP) as exF:
                if file[file.__len__()-5:file.__len__()] == "dslog" and file not in exF.read():
                    fp=self.dsLogDir+"/"+file
                    newDSLP=dslp.DSLogParser(fp)
                    newDSLP.read_records()
                    v=newDSLP.read_record_v3()
                    Path.open(os.path.join(self.destinationDr,file[0:file.__len__()-6]+".csv"), "x")
                    self.addToExclusionList(file)

    def addToExclusionList(self,fileName=""):
        if Path(self.exclusionListFP).is_file:
            open(os.path.join(os.path.dirname(os.path.realpath(__file__)),"exclusionListFP.txt"), "a")
        else:
            open(os.path.join(os.path.dirname(os.path.realpath(__file__)),"exclusionListFP.txt"), "x")

        with Path.open(self.exclusionListFP,"a") as f:
            f.write(fileName+"\n")

dslogdir=r"C://Users/Public\Documents/FRC/Log Files\DSLogs"

dsconv=DSConvertor(dslogdir)

dsconv.processDSLogs()