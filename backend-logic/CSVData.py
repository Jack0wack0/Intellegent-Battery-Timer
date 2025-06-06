import csv

class _CSVFunctions:
    """
    Private class for basic functions used by the functions in CSVData
    """
    def __init__(self,columns,rows):
        self.columns=columns
        self.rows=rows

    def columnValues(self,targetColumn=""):
        output=[]
        i=0

        for column in self.columns:
            if(targetColumn==column):
                for row in self.rows:
                    if(row!=self.rows[0]):
                        if(row):
                            output.append((row[i]))
            else:
                i+=1
        
        return output
    
class CSVData:
    """
    Class for manipulating and pulling information from csv files.

    Functions
    -------------------------------------------------------------------------------
    getColumnValues(), deleteColumns(), deleteRows(), findUnique(), oneHotEncode()

    -------------------------------------------------------------------------------

    Params
    -------------------------------------------------------------------------------
    csvFile: Requires the directory of a csvFile to be passed in.

    -------------------------------------------------------------------------------
    """
    def __init__(self,csvFile="",encoding=""):
        if encoding=="":
            with open(csvFile) as f:
                reader=list(csv.reader(f))
                rows=reader.copy()
        else:
            with open(csvFile,encoding=encoding) as f:
                reader=list(csv.reader(f))
                rows=reader.copy()

        self.rows=rows
        self.rowCount=len(rows)
        self.csvFile=csvFile
        self.encoding=encoding

        if len(rows)!=0:
            self.columns=rows[0]
            self.columnCount=len(rows[0])
            self.csvFuncs=_CSVFunctions(self.columns,self.rows)

    def getColumnValues(self,targetColumn=""):
        """
        Returns the columns values.

        Params
        -------------------------------------------------------------------------------
        targetColumn: Requires the name of the column with the desired values to be passed in.

        -------------------------------------------------------------------------------
        """
        return self.csvFuncs.columnValues(targetColumn)
    
    def deleteColumns(self,targetColumns=[""]):
        """
        Returns a new set of data with only the desired columns.

        Params
        -------------------------------------------------------------------------------
        targetColumns: List of columns to remove, uses the name of column.

        -------------------------------------------------------------------------------
        """
        outputList=[]
        targetColumnIndexs=[]
        newRow=[]
        i=0

        for column in self.columns:
            for targetColumn in targetColumns:
                if(targetColumn==column):
                    targetColumnIndexs.append(i)
                    i=0
                else:
                    i+=1
     
        for row in self.rows:
            for element in range(self.rowCount):
                if(any(element==e for e in targetColumnIndexs)==False):
                    newRow.append(row[element])
                    outputList.append(newRow)
    
        return outputList
    
    def deleteRows(self,targetRows=[0]):
        """
        Returns a new set of data with only the desired rows.

        Params
        -------------------------------------------------------------------------------
        targetRows: List of rows to remove, uses the index of the row.

        -------------------------------------------------------------------------------
        Also when removing rows a row index of 0 is always the column names.
        """
        outputList=[]

        for row in range(self.rowCount):
            if(any(row==r for r in targetRows)==False):
                outputList.append(self.rows[row])

        return outputList
    
    def writeRowValues(self,csvFile,rowValues=[]):
        if self.encoding=="":
            with open(csvFile,"w",newline='') as f:
                writer=csv.writer(f)
                writer.writerows(rowValues)
        else:
            with open(csvFile,"w",newline='',encoding=self.encoding) as f:
                writer=csv.writer(f)
                writer.writerows(rowValues)
    
    def writeSingleRowValue(self,csvFile,rowValue=[]):
        if self.encoding=="":
            with open(csvFile,"w",newline='') as f:
                writer=csv.writer(f)
                writer.writerow(rowValue)
        else:
            with open(csvFile,"w",newline='',encoding=self.encoding) as f:
                writer=csv.writer(f)
                writer.writerow(rowValue)

    def findUnique(self,targetColumn=""):
        """
        Returns all the unique values in a column.

        Params
        -------------------------------------------------------------------------------
        targetColumn: The column in which you want to grab the unique values from.

        -------------------------------------------------------------------------------
        """
        uniqueValues=[]
        values=[]
        i=0

        values=self.csvFuncs.columnValues(targetColumn)

        for value in values:
            for i in range(len(values)):
                if(value==values[i]):
                    if(len(uniqueValues)==0):
                        uniqueValues.append(value)
                    else:
                        if values[i] not in uniqueValues:
                            uniqueValues.append(value)

        #print(uniqueValues)
        return uniqueValues

    def oneHotEncode(self,uniqueValues,targetColumn=""):
        """
        Using unique values from the same column this will return a new one-hot matrix.

        Params
        -------------------------------------------------------------------------------
        uniqueValues: Unique values from the same column.

        targetColumn: The column you want to one-hot encode.

        -------------------------------------------------------------------------------
        """
        outputMatrix=[]
        values=[]
        i=0

        values=self.csvFuncs.columnValues(targetColumn)

        for value in values:
            newMatrixRow=[]

            for i in range(len(uniqueValues)):
                if(value==uniqueValues[i]):
                    newMatrixRow.append(1)
                else:
                    newMatrixRow.append(0)

                if i==max(range(len(uniqueValues))):
                    outputMatrix.append(newMatrixRow)

        #print(uniqueTokens)
        #for row in outputMatrix:
        #    print(row)
        return outputMatrix
    