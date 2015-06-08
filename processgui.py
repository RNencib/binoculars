import sys,os 
import itertools
import inspect
import glob
import BINoculars.util, BINoculars.main
import time
from PyQt4.QtGui import *
from PyQt4.QtCore import *


#--------------------------------------------CREATE MAIN WINDOW----------------------------------------
class SimpleGUI(QMainWindow):

    def __init__(self):
        super(SimpleGUI, self).__init__()
        self.initUI()
        self.tab_widget = QTabWidget(self)
        self.setCentralWidget(self.tab_widget)
        #add the close button for tabs
        close = self.tab_widget.setTabsClosable(True)
        self.tab_widget.tabCloseRequested.connect(self.close_tab)

    #method for close tabs
    def close_tab(self, tab):
        self.tab_widget.removeTab(tab)

    def initUI(self):
        #we create the menu bar
        openFile = QAction('Open', self)
        openFile.setShortcut('Ctrl+O')
        openFile.setStatusTip('Open new File')
        openFile.triggered.connect(self.showFile)

        saveFile = QAction('Save', self)
        saveFile.setShortcut('Ctrl+S')
        saveFile.setStatusTip('Save File')
        saveFile.triggered.connect(self.Save)

        Create = QAction('Create', self)
        Create.setStatusTip('Create new configuration')
        Create.triggered.connect(self.New_Config)


        menubar = self.menuBar()
        fileMenu = menubar.addMenu('&File')
        fileMenu.addAction(openFile)
        fileMenu.addAction(saveFile)
        fileMenu = menubar.addMenu('&New Configuration')
        fileMenu.addAction(Create)

        #we configue the main windows
        palette = QPalette()
        palette.setColor(QPalette.Background,Qt.gray)
        self.setPalette(palette)
        #self.setGeometry(250, 100,500,500)
        self.setWindowTitle('Binoculars')
        self.setWindowIcon(QIcon('binoculars.png'))
        self.showMaximized()

    #we call the load function
    def showFile(self):
        filename = QFileDialog.getOpenFileName(self, 'Open File', '')
        for F in filename.split('/') :
            NameFile = []
            NameFile.append(F)
        NameFile.reverse()
        if NameFile[0].isEmpty() == False:
            newIndex =  self.tab_widget.addTab(Conf_Tab(self),NameFile[0])
            self.tab_widget.setCurrentIndex(newIndex)
            widget = self.tab_widget.currentWidget()
            widget.read_data(filename)

    #we call the save function
    def Save(self):
        filename = QFileDialog().getSaveFileName(self, 'Enregistrer', '', '*.txt')
        widget = self.tab_widget.currentWidget() 
        widget.save(filename) 

    #we call the new tab conf   
    def New_Config(self):
        self.tab_widget.addTab(Conf_Tab(self),'New configuration')


#----------------------------------------------------------------------------------------------------
#-----------------------------------------CREATE TABLE-----------------------------------------------
class Table(QWidget):
    def __init__(self, parent = None):
        super(Table, self).__init__()
        
        # create a QTableWidget
        self.table = QTableWidget(1, 2, self)
        self.table.setHorizontalHeaderLabels(['Parameter', 'Value','Comment'])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.verticalHeader().setVisible(False)
        
        #create combobox
        self.combobox = QComboBox()
        #add items
        self.cell = QTableWidgetItem(QString("type"))
        self.table.setItem(0, 0,self.cell)
        self.table.setCellWidget(0, 1, self.combobox)
        #we create pushbuttons and we call the method when we clic on 
        self.btn_add_row = QPushButton('+', self)
        self.connect(self.btn_add_row, SIGNAL('clicked()'), self.add_row)
        self.buttonRemove = QPushButton('-',self)
        self.connect(self.buttonRemove, SIGNAL("clicked()"), self.remove)
        self.btn_add_row.resize(10,10)
        self.buttonRemove.resize(10,10) 
        #the dispositon of the table and the butttons
        layout =QGridLayout()
        layout.addWidget(self.table,1,0,1,0)
        layout.addWidget(self.btn_add_row,0,0)
        layout.addWidget(self.buttonRemove,0,1)
        self.setLayout(layout)

    def add_row(self):
        self.table.insertRow(self.table.rowCount())
    
    def remove(self):
        self.table.removeRow(self.table.currentRow()) 

    def get_keys(self):
        return list(self.table.item(index,0).text() for index in range(self.table.rowCount())) 

    #Here we take all values on tables
    def getParam(self):
        for index in range(self.table.rowCount()):
            key = str(self.table.item(index,0).text())
            comment = str(self.table.item(index,0).toolTip())
            if self.table.item(index,1):
                value = str(self.table.item(index, 1).text())
            else:
                value = str(self.table.cellWidget(index, 1).currentText())
            if self.table.item == None:
                value = str(self.table.item(index,1).text(""))
            yield key, value, comment

    #Here we put all values on tables   
    def addData(self, data):
        for item in data:
            if item[0] == 'type':
                box = self.table.cellWidget(0,1)
                box.setCurrentIndex(box.findText(item[1], Qt.MatchFixedString))
                self.cell.setToolTip(item[2])
            else: 
                self.add_row()
                row = self.table.rowCount()
                for col in range(self.table.columnCount()):
                    self.newitem = QTableWidgetItem(item[col])
                    self.table.setItem(row -1, col, self.newitem)
                    self.newitem.setToolTip(item[2])
                        

    def addDataConf(self, items):
        keys = self.get_keys()
        newconfigs = list([item[0], '', item[1]] for item in items if item[0] not in keys)
        self.addData(newconfigs)
                
    def add_to_combo(self, items):
        self.combobox.clear()
        self.combobox.addItems(items)
    

#----------------------------------------------------------------------------------------------------
#-----------------------------------------CREATE CONFIG----------------------------------------------
class Conf_Tab(QWidget):
    def __init__(self, parent = None):

        super(Conf_Tab,self).__init__()
        #we create 3 tables
        self.Dis = Table()
        self.Inp = Table()
        self.Pro = Table()

        label1 = QLabel('<strong>Dispatcher</strong>')
        label2 = QLabel('<strong>Input</strong>')
        label3 = QLabel('<strong>Projection<strong>')

        self.select = QComboBox()
        backends = list(backend.lower() for backend in BINoculars.util.get_backends())
        #we add the list of different backends on the select combobox
        self.select.addItems(QStringList(backends))
        self.start = QPushButton('run')
        self.connect(self.start, SIGNAL("clicked()"), self.run)
        self.scan = QLineEdit()
        self.scan.setToolTip('scan selection exemple: 820 824')
        self.start.setStyleSheet("background-color: darkred")

        #the dispositon of all elements of the gui
        Layout = QGridLayout()
        Layout.addWidget(label1,0,2)
        Layout.addWidget(label2,0,1)
        Layout.addWidget(label3,0,3)
        Layout.addWidget(self.select,0,0)
        Layout.addWidget(self.Dis,1,2)
        Layout.addWidget(self.Inp,1,1)
        Layout.addWidget(self.Pro,1,3) 
        Layout.addWidget(self.start,2,0)
        Layout.addWidget(self.scan,2,1)
        self.setLayout(Layout)
        
        #Here we call all methods for selected an ellement on differents combobox 
        self.Dis.add_to_combo(QStringList(BINoculars.util.get_dispatchers()))
        self.select.activated['QString'].connect(self.DataCombo)
        self.Inp.combobox.activated['QString'].connect(self.DataTableInp)
        self.Pro.combobox.activated['QString'].connect(self.DataTableInpPro)
        self.Dis.combobox.activated['QString'].connect(self.DataTableInpDis)
        

    def DataCombo(self,text):
        self.Inp.add_to_combo(QStringList(BINoculars.util.get_inputs(str(text))))
        self.Pro.add_to_combo(QStringList(BINoculars.util.get_projections(str(text))))

    def DataTableInp (self,text):
        backend = str(self.select.currentText())
        inp = BINoculars.util.get_input_configkeys(backend, str(self.Inp.combobox.currentText()))
        self.Inp.addDataConf(inp)

    def DataTableInpPro (self,text):
        backend = str(self.select.currentText())
        proj = BINoculars.util.get_projection_configkeys(backend, str(self.Pro.combobox.currentText()))
        self.Pro.addDataConf(proj)

    def DataTableInpDis (self,text):
        backend = str(self.select.currentText())
        disp = BINoculars.util.get_dispatcher_configkeys(str(self.Dis.combobox.currentText()))
        self.Dis.addDataConf(disp)

    #The save method we take all ellements on tables and we put them in this format {0} = {1} #{2}
    def save(self, filename): 
        with open(filename, 'w') as fp:
            fp.write('[dispatcher]\n')
            # cycles over the iterator object
            for key, value, comment in self.Dis.getParam():
                fp.write('{0} = {1} #{2}\n'.format(key, value, comment))
            fp.write('[input]\n')
            for key, value, comment in self.Inp.getParam():
                if key == 'type':
                    value = '{0}:{1}'.format(self.select.currentText(),value)
                fp.write('{0} = {1} #{2}\n'.format(key, value, comment))
            fp.write('[projection]\n')
            for key, value, comment in self.Pro.getParam():
                if key == 'type':
                    value = '{0}:{1}'.format(self.select.currentText(),value)
                fp.write('{0} = {1} #{2}\n'.format(key, value, comment))

    #This method take the name of objects and values for run the script
    def get_configobj(self):

        inInp = {}
        inDis = {}
        inPro = {}

        InDis = dict((key, value) for key, value, comment in self.Dis.getParam())

        for key, value, comment in self.Inp.getParam():
            if key == 'type':
                value = '{0}:{1}'.format(self.select.currentText(),value)
            inInp[key] = value 

        for key, value, comment in self.Pro.getParam():
            if key == 'type':
                value = '{0}:{1}'.format(self.select.currentText(),value)
            inPro[key] = value

        cfg = BINoculars.util.ConfigFile('gui {0}'.format(time.strftime('%d %b %Y %H:%M:%S', time.localtime())))
        setattr(cfg, 'input', inInp)
        setattr(cfg, 'dispatcher', inDis)
        setattr(cfg, 'projection', inPro)
        return cfg

    #This method take elements on a text file or the binocular script and put them on tables
    def read_data(self,filename):
        with open(filename, 'r') as inf:
            lines = inf.readlines()
 
        data = {'dispatcher': [], 'input': [], 'projection': []}
        for line in lines:
            line = line.strip('\n')
            if '[dispatcher]' in line:
                key = 'dispatcher'
            elif '[input]' in line:
                key = 'input'
            elif '[projection]' in line: 
                key = 'projection'
            else:
                if '#' in line:
                    index = line.index('#')
                    caput = line[:index]
                    cauda = line[index:]
                else:
                    caput = line
                    cauda = ''
                if '=' in caput:
                    name, value = caput.split('=')
                    if name.strip(' ') == 'type' and ':' in value:
                        backend, value = value.strip(' ').split(':')
                    data[key].append([name.strip(' '), value.strip(' '), cauda.strip(' ')])

        self.select.setCurrentIndex(self.select.findText(backend, Qt.MatchFixedString))
        self.DataCombo(backend)
        for key in data:
            if key == 'dispatcher':
                self.Dis.addData(data[key])
            elif key == 'input':
                self.Inp.addData(data[key])
            elif key == 'projection':
                self.Pro.addData(data[key])

    #We run the script and create a hdf5 file            
    def run(self):
        command = [str(self.scan.text())]
        cfg = self.get_configobj()
        BINoculars.main.Main.from_object(cfg, command)



