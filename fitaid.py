import h5py
import sys
import numpy
import os.path
from PyQt4 import QtGui, QtCore, Qt
import BINoculars.main, BINoculars.space, BINoculars.plot, BINoculars.fit, BINoculars.util
from scipy.interpolate import griddata

from matplotlib.backends.backend_qt4agg import FigureCanvasQTAgg, NavigationToolbar2QTAgg
import matplotlib.figure, matplotlib.image
from matplotlib.pyplot import Rectangle
import itertools
from scipy.spatial import qhull

class Window(QtGui.QMainWindow):
    def __init__(self, parent=None):
        super(Window, self).__init__(parent)

        newproject = QtGui.QAction("New project", self)  
        newproject.triggered.connect(self.newproject)

        loadproject = QtGui.QAction("Open project", self)  
        loadproject.triggered.connect(self.loadproject)

        addspace = QtGui.QAction("Import space", self)  
        addspace.triggered.connect(self.add_to_project)

        menu_bar = QtGui.QMenuBar() 
        file = menu_bar.addMenu("&File") 
        file.addAction(newproject)
        file.addAction(loadproject)
        file.addAction(addspace)

        self.setMenuBar(menu_bar)
        self.statusbar	= QtGui.QStatusBar()

        self.tab_widget = QtGui.QTabWidget(self)
        self.tab_widget.setTabsClosable(True)
        QtCore.QObject.connect(self.tab_widget, QtCore.SIGNAL("tabCloseRequested(int)"), self.tab_widget.removeTab)

        self.setCentralWidget(self.tab_widget)
        self.setMenuBar(menu_bar)
        self.setStatusBar(self.statusbar)

    def newproject(self):
        dialog = QtGui.QFileDialog(self, "project filename");
        dialog.setFilter('BINoculars fit file (*.fit)');
        dialog.setDefaultSuffix('fit');
        dialog.setFileMode(QtGui.QFileDialog.AnyFile);
        dialog.setAcceptMode(QtGui.QFileDialog.AcceptSave);
        if not dialog.exec_():
            return
        fname = dialog.selectedFiles()[0]
        if not fname:
            return
        try:
            widget = TopWidget(str(fname), parent=self)
            self.tab_widget.addTab(widget, short_filename(str(fname)))
            self.tab_widget.setCurrentWidget(widget)
        except Exception as e:
            QtGui.QMessageBox.critical(self, 'New project', 'Unable to save project to {}: {}'.format(fname, e))

    def loadproject(self, filename = None):
        if not filename:
            dialog = QtGui.QFileDialog(self, "Load project");
            dialog.setFilter('BINoculars fit file (*.fit)');
            dialog.setFileMode(QtGui.QFileDialog.ExistingFiles);
            dialog.setAcceptMode(QtGui.QFileDialog.AcceptOpen);
            if not dialog.exec_():
                return
            fname = dialog.selectedFiles()[0]
            if not fname:
                return
            try:
                widget = TopWidget(str(fname), parent=self)
                self.tab_widget.addTab(widget, short_filename(str(fname)))
                self.tab_widget.setCurrentWidget(widget)
            except Exception as e:
                QtGui.QMessageBox.critical(self, 'Load project', 'Unable to load project from {}: {}'.format(fname, e))
        else:
            widget = TopWidget(str(fname), parent=self)
            self.tab_widget.addTab(widget, 'fname')
            self.tab_widget.setCurrentWidget(widget)

    def add_to_project(self, filename = None):
        if self.tab_widget.count() == 0:
            QtGui.QMessageBox.warning(self, 'Warning', 'First select a file to store data')
            self.newproject()
            
        if not filename:
            dialog = QtGui.QFileDialog(self, "Import spaces");
            dialog.setFilter('BINoculars space file (*.hdf5)');
            dialog.setFileMode(QtGui.QFileDialog.ExistingFiles);
            dialog.setAcceptMode(QtGui.QFileDialog.AcceptOpen);
            if not dialog.exec_():
                return
            fname = dialog.selectedFiles()
            if not fname:
                return
            for name in fname:
                try:
                    widget = self.tab_widget.currentWidget()
                    widget.addspace(str(name))
                except Exception as e:
                    QtGui.QMessageBox.critical(self, 'Import spaces', 'Unable to import space {}: {}'.format(fname, e))
        else:
            widget = self.tab_widget.currentWidget()
            widget.addspace(filename)
     

class TopWidget(QtGui.QWidget):
    def __init__(self, filename , parent=None):
        super(TopWidget, self).__init__(parent)

        hbox = QtGui.QHBoxLayout() 
        vbox = QtGui.QVBoxLayout() 
        minihbox =  QtGui.QHBoxLayout() 
        minihbox2 =  QtGui.QHBoxLayout() 

        self.database = FitData(filename)
        self.table = TableWidget(self.database)
        self.nav = ButtonedSlider()
        self.nav.connect(self.nav, QtCore.SIGNAL('slice_index'), self.index_change)
        self.table.trigger.connect(self.active_change)
        self.table.check_changed.connect(self.refresh_plot)
        self.tab_widget = QtGui.QTabWidget()

        self.fitwidget = FitWidget(self.database)
        self.integratewidget = IntegrateWidget(self.database)
        self.plotwidget = OverviewWidget(self.database)

        self.tab_widget.addTab(self.fitwidget, 'Fit')
        self.tab_widget.addTab(self.integratewidget, 'Integrate')
        self.tab_widget.addTab(self.plotwidget, 'plot')

        self.emptywidget = QtGui.QWidget()
        self.emptywidget.setLayout(vbox) 

        vbox.addWidget(self.table)
        vbox.addWidget(self.nav)

        self.functions = list()
        self.function_box = QtGui.QComboBox()        
        for function in dir(BINoculars.fit):
            cls = getattr(BINoculars.fit, function)
            if isinstance(cls, type) and issubclass(cls, BINoculars.fit.PeakFitBase):
                self.functions.append(cls)
                self.function_box.addItem(function)
        self.function_box.setCurrentIndex(self.function_box.findText('PolarLorentzian2D'))

        vbox.addWidget(self.function_box)
        vbox.addLayout(minihbox)
        vbox.addLayout(minihbox2)
        
        self.all_button = QtGui.QPushButton('fit all')
        self.rod_button = QtGui.QPushButton('fit rod')
        self.slice_button = QtGui.QPushButton('fit slice')

        self.all_button.clicked.connect(self.fit_all)
        self.rod_button.clicked.connect(self.fit_rod)
        self.slice_button.clicked.connect(self.fit_slice)

        minihbox.addWidget(self.all_button)
        minihbox.addWidget(self.rod_button)
        minihbox.addWidget(self.slice_button)

        self.allint_button = QtGui.QPushButton('int all')
        self.rodint_button = QtGui.QPushButton('int rod')
        self.sliceint_button = QtGui.QPushButton('int slice')

        self.allint_button.clicked.connect(self.int_all)
        self.rodint_button.clicked.connect(self.int_rod)
        self.sliceint_button.clicked.connect(self.int_slice)

        minihbox2.addWidget(self.allint_button)
        minihbox2.addWidget(self.rodint_button)
        minihbox2.addWidget(self.sliceint_button)

        splitter = QtGui.QSplitter(QtCore.Qt.Horizontal)

        splitter.addWidget(self.emptywidget)
        splitter.addWidget(self.tab_widget)
        self.tab_widget.currentChanged.connect(self.tab_change)

        hbox.addWidget(splitter) 
        self.setLayout(hbox) 

    def tab_change(self, index):
        if index == 2:
            self.refresh_plot()

    def addspace(self,filename = None):
        if filename == None:
            filename = str(QtGui.QFileDialog.getOpenFileName(self, 'Open Project', '.', '*.hdf5'))
        self.table.addspace(filename)

    def active_change(self):
        rodkey, axis, resolution = self.table.currentkey()
        newdatabase = RodData(self.database.filename, rodkey, axis, resolution)
        self.integratewidget.database = newdatabase
        self.integratewidget.set_axis()
        self.fitwidget.database = newdatabase
        self.nav.set_length(newdatabase.rodlength())
        index = newdatabase.load('index')
        if index == None:
            index = 0
        self.nav.set_index(index)
        self.index_change(index)

    def index_change(self, index):
        if index == None:
            index = 0
        self.fitwidget.database.save('index', self.nav.index())
        self.fitwidget.plot(index)
        self.integratewidget.plot(index)

    def refresh_plot(self):
        self.plotwidget.refresh(list(RodData(self.database.filename, rodkey, axis, resolution) for rodkey, axis, resolution in self.table.checked()))

    @property
    def fitclass(self):
        return self.functions[self.function_box.currentIndex()]

    def fit_slice(self):
        index = self.nav.index()
        space = self.fitwidget.database.space_from_index(index)
        self.fitwidget.fit(index, space, self.fitclass)
        self.fit_loc(self.fitwidget.database)
        self.fitwidget.plot(index)

    def fit_rod(self):
        def function(index, space):
            self.fitwidget.fit(index, space, self.fitclass)
        self.progressbox(self.fitwidget.database.rodkey, function, enumerate(self.fitwidget.database), self.fitwidget.database.rodlength())
        self.fit_loc(self.fitwidget.database)
        self.fitwidget.plot()


    def fit_all(self):
        def function(index, space):
            self.fitwidget.fit(index, space, self.fitclass)

        for rodkey, axis, resolution in self.table.checked():
            self.fitwidget.database = RodData(self.database.filename, rodkey, axis, resolution)
            self.progressbox(self.fitwidget.database.rodkey, function, enumerate(self.fitwidget.database), self.fitwidget.database.rodlength())
            self.fit_loc(self.fitwidget.database)

        self.fitwidget.plot()


    def int_slice(self):
        index = self.nav.index()
        space = self.fitwidget.database.space_from_index(index)
        self.integratewidget.integrate(index, space)
        self.integratewidget.plot(index)

    def int_rod(self):
        self.progressbox(self.integratewidget.database.rodkey,self.integratewidget.integrate, enumerate(self.integratewidget.database), self.integratewidget.database.rodlength())
        self.integratewidget.plot()

    def int_all(self):
        for rodkey, axis, resolution in self.table.checked():
            self.integratewidget.database = RodData(self.database.filename, rodkey, axis, resolution)
            self.progressbox(self.integratewidget.database.rodkey,self.integratewidget.integrate, enumerate(self.integratewidget.database), self.integratewidget.database.rodlength())
        self.integratewidget.plot()
  
    def fit_loc(self, database):
        deg = 2
        for param in database.all_attrkeys():
            if param.startswith('loc'):
                x, y = database.all_from_key(param)
                x, yvar = database.all_from_key('var_{0}'.format(param))
                cx = x[numpy.invert(y.mask)]
                y = y.compressed()
                yvar = yvar.compressed()

                w = numpy.log(1 / yvar)
                w[w == numpy.inf] = 0
                w = numpy.nan_to_num(w)
                w[w < 0] = 0
                w[w < numpy.median(w)] = 0
                if len(x) > 0:
                    c = numpy.polynomial.polynomial.polyfit(cx, y, deg, w = w)
                    newy = numpy.polynomial.polynomial.polyval(x, c)
                    for index, newval in enumerate(newy):
                        database.save_sliceattr(index, 'guessloc{0}'.format(param.lstrip('loc')) , newval)

    def progressbox(self, rodkey , function, iterator, length):
        pd = QtGui.QProgressDialog('Processing {0}'.format(rodkey), 'Cancel', 0, length)
        pd.setWindowModality(QtCore.Qt.WindowModal)
        pd.show()
        def progress(index, item):
            pd.setValue(index)
            if pd.wasCanceled():
                raise KeyboardInterrupt
            QtGui.QApplication.processEvents()
            function(*item)
        for index, item in enumerate(iterator):
            progress(index, item)
        pd.close()

class TableWidget(QtGui.QWidget):
    trigger = QtCore.pyqtSignal()
    check_changed = QtCore.pyqtSignal()

    def __init__(self, database, parent=None):
        super(TableWidget, self).__init__(parent)

        hbox = QtGui.QHBoxLayout()
        self.database = database

        self.activeindex = 0

        self.table = QtGui.QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(['','rod', 'axis', 'res', 'remove'])
        
        self.table.cellClicked.connect(self.setlength)

        for index, width in enumerate([25,150,40,50,70]):
            self.table.setColumnWidth(index, width)

        for filename, rodkey in zip(database.filelist, database.rods()):
            self.addspace(filename, rodkey)

        hbox.addWidget(self.table)
        self.setLayout(hbox)

    def addspace(self, filename, rodkey = None):
        def remove_callback(rodkey):
            return lambda: self.remove(rodkey)

        def activechange_callback(index):
            return lambda: self.setlength(index, 1)

        if rodkey == None:
            rodkey = short_filename(filename)
            if rodkey in self.database.rods():
                newkey =  find_unused_rodkey(rodkey, self.database.rods())
                self.database.copy(rodkey, newkey)
                rodkey = newkey

        old_axis, old_resolution = self.database.load(rodkey, 'axis'), self.database.load(rodkey, 'resolution')
        self.database.create_rod(rodkey, filename)
        index = self.table.rowCount()
        self.table.insertRow(index)


        axes = BINoculars.space.Axes.fromfile(filename) 

        checkboxwidget = QtGui.QCheckBox()
        checkboxwidget.rodkey = rodkey
        checkboxwidget.setChecked(0)
        self.table.setCellWidget(index,0, checkboxwidget)
        checkboxwidget.clicked.connect(self.check_changed)

        item = QtGui.QTableWidgetItem(rodkey)
        self.table.setItem(index, 1, item)

        axis = QtGui.QComboBox()
        for ax in axes:
            axis.addItem(ax.label)
        self.table.setCellWidget(index, 2, axis)
        if not old_axis == None:
            self.table.cellWidget(index, 2).setCurrentIndex(axes.index(old_axis))
        elif index > 0:
            self.table.cellWidget(0, 2).setCurrentIndex(self.table.cellWidget(0,2).currentIndex())

        resolution = QtGui.QLineEdit()
        if not old_resolution == None:
            resolution.setText(str(old_resolution))
        elif index > 0:
            resolution.setText(self.table.cellWidget(0,3).text())
        else:
            resolution.setText(str(axes[axes.index(str(axis.currentText()))].res))
        
        resolution.editingFinished.connect(activechange_callback(index))
        self.table.setCellWidget(index, 3, resolution)
        
        buttonwidget = QtGui.QPushButton('remove')
        buttonwidget.clicked.connect(remove_callback(rodkey))
        self.table.setCellWidget(index,4, buttonwidget)

    def remove(self, rodkey):
        table_rodkeys = list(self.table.cellWidget(index, 0).rodkey for index in range(self.table.rowCount()))
        for index, label in enumerate(table_rodkeys):
            if rodkey == label:
                self.table.removeRow(index)
        self.database.delete_rod(rodkey)
        print 'removed: {0}'.format(rodkey)

    def setlength(self, y, x = 1):
        if x == 1:
            self.activeindex = y
            rodkey, axis, resolution = self.currentkey()
            self.database.save(rodkey, 'axis', axis)
            self.database.save(rodkey, 'resolution', resolution)
            self.trigger.emit()

    def currentkey(self):
        rodkey = self.table.cellWidget(self.activeindex, 0).rodkey
        axis = str(self.table.cellWidget(self.activeindex,2).currentText())
        resolution = float(self.table.cellWidget(self.activeindex,3).text())
        return rodkey, axis, resolution

    def checked(self):
        selection = []
        for index in range(self.table.rowCount()):
            checkbox = self.table.cellWidget(index, 0)
            if checkbox.checkState():
                rodkey = self.table.cellWidget(index, 0).rodkey
                axis = str(self.table.cellWidget(index,2).currentText())
                resolution = float(self.table.cellWidget(index,3).text())
                selection.append((rodkey, axis, resolution))
        return selection

class FitData(object):
    def __init__(self, filename):
        self.filename = filename
        self.axdict = dict()
        
        with h5py.File(self.filename,'a') as db:
            for rodkey in self.rods():
                spacename = db[rodkey].attrs['filename']   
                if not os.path.exists(spacename):
                    warningbox = QtGui.QMessageBox(2, 'Warning', 'Cannot find space {0} at file {1}; locate proper space'.format(rodkey, spacename), buttons = QtGui.QMessageBox.Open)
                    warningbox.exec_()
                    spacename = str(QtGui.QFileDialog.getOpenFileName(caption = 'Open space {0}'.format(rodkey), directory = '.', filter = '*.hdf5'))
                    if not spacename:
                        raise IOError('Select proper input')
                    db[rodkey].attrs['filename'] = spacename
                self.axdict[rodkey] = BINoculars.space.Axes.fromfile(spacename)    

    def create_rod(self, rodkey, spacename):
        with h5py.File(self.filename,'a') as db:
            if rodkey not in db.keys():
                db.create_group(rodkey)
                db[rodkey].attrs['filename'] =  spacename
                self.axdict[rodkey] = BINoculars.space.Axes.fromfile(spacename)

    def delete_rod(self, rodkey):
        with h5py.File(self.filename,'a') as db:
            del db[rodkey]

    def rods(self):
        with h5py.File(self.filename,'a') as db:
            rods = db.keys()
        return rods

    def copy(self, oldkey, newkey):
        with h5py.File(self.filename,'a') as db:
            if oldkey in db.keys():
                db.copy(db[oldkey], db, name = newkey) 
          
    @property
    def filelist(self):
        filelist = []
        with h5py.File(self.filename,'a') as db:
            for key in db.iterkeys():
                filelist.append(db[key].attrs['filename'])
        return filelist

    def save(self, rodkey, key, value):
        with h5py.File(self.filename,'a') as db:
             db[rodkey].attrs[str(key)] = value

    def load(self, rodkey, key):
        with h5py.File(self.filename,'a') as db:
            if rodkey in db:
                if key in db[rodkey].attrs:
                    return db[rodkey].attrs[str(key)]                         
            else:
                return None

class RodData(FitData):
    def __init__(self, filename, rodkey, axis, resolution):
        super(RodData, self).__init__(filename)
        self.rodkey = rodkey
        self.slicekey = '{0}_{1}'.format(axis, resolution)
        self.axis = axis
        self.resolution = resolution

        with h5py.File(self.filename,'a') as db:
            if rodkey in db:
                if self.slicekey not in db[rodkey]:
                    db[rodkey].create_group(self.slicekey)
                    db[rodkey][self.slicekey].create_group('attrs')

    def save(self, key, value):
        super(RodData, self).save(self.rodkey, key, value)

    def load(self, key):
        return super(RodData, self).load(self.rodkey, key)

    def paxes(self):
        axes = self.axdict[self.rodkey]
        projected = list(axes)
        axindex = axes.index(self.axis)
        projected.pop(axindex)
        return projected

    def get_bins(self):
        axes = self.axdict[self.rodkey]
        axindex = axes.index(self.axis)
        ax = axes[axindex]

        bins = BINoculars.space.get_bins(ax, self.resolution)
        return bins, ax, axindex
       
    def rodlength(self):
        bins, ax, axindex = self.get_bins()
        return numpy.alen(bins) - 1 

    def get_index_value(self, index):
        return BINoculars.space.get_axis_values(self.axdict[self.rodkey], self.axis, self.resolution)[index]

    def get_key(self, index):
        axes = self.axdict[self.rodkey]
        bins, ax, axindex = self.get_bins()
        start, stop = bins[index], bins[index + 1]
        k = [slice(None) for i in axes]
        k[axindex] = slice(start, stop)
        return k
            
    def space_from_index(self, index):
        with h5py.File(self.filename,'a') as db:
             filename = db[self.rodkey].attrs['filename']
        return BINoculars.space.Space.fromfile(filename, self.get_key(index)).project(self.axis)

    def save_data(self, index, key, data):         
        with h5py.File(self.filename,'a') as db:
            id = '{0}_{1}_data'.format(int(index), key)
            mid = '{0}_{1}_mask'.format(int(index), key)
            try:
                db[self.rodkey][self.slicekey].create_dataset(id, data.shape, dtype=data.dtype, compression='gzip').write_direct(data)
                db[self.rodkey][self.slicekey].create_dataset(mid, data.shape, dtype=data.mask.dtype, compression='gzip').write_direct(data.mask)
            except RuntimeError:
                del db[self.rodkey][self.slicekey][id]
                del db[self.rodkey][self.slicekey][mid]
                db[self.rodkey][self.slicekey].create_dataset(id, data.shape, dtype=data.dtype, compression='gzip').write_direct(data)
                db[self.rodkey][self.slicekey].create_dataset(mid, data.shape, dtype=data.mask.dtype, compression='gzip').write_direct(data.mask)

    def load_data(self, index, key):   
        with h5py.File(self.filename,'a') as db:
            id = '{0}_{1}_data'.format(int(index), key)
            mid = '{0}_{1}_mask'.format(int(index), key)
            try:
                return numpy.ma.array(db[self.rodkey][self.slicekey][id][...], mask = db[self.rodkey][self.slicekey][mid][...])
            except KeyError:
                return None

    def save_sliceattr(self, index, key, value):
        mkey = 'mask{0}'.format(key)
        with h5py.File(self.filename,'a') as db:
            try:
                group = db[self.rodkey][self.slicekey]['attrs']## else it breaks with the old fitaid
            except KeyError: 
                db[rodkey][slicekey].create_group('attrs')
                group = db[self.rodkey][self.slicekey]['attrs']
            if not key in group:
                group.create_dataset(key, (self.rodlength(),))
                group.create_dataset(mkey, (self.rodlength(),), dtype = numpy.bool).write_direct(numpy.ones(self.rodlength(), dtype = numpy.bool))
            group[key][index] = value
            group[mkey][index] = 0


    def load_sliceattr(self, index, key):
        mkey = 'mask{0}'.format(key)
        with h5py.File(self.filename,'a') as db:
            try:
                group = db[self.rodkey][self.slicekey]['attrs']
            except KeyError: 
                db[self.rodkey][self.slicekey].create_group('attrs')
                group = db[self.rodkey][self.slicekey]['attrs']
            if key in group.keys():
                return numpy.ma.array(group[key][index], mask = group[mkey][index])  
            else:               
                return None

    def all_attrkeys(self):
        with h5py.File(self.filename,'a') as db:
            group = db[self.rodkey][self.slicekey]['attrs']
            return group.keys() 

    def all_from_key(self, key):
        mkey = 'mask{0}'.format(key)
        axes = self.axdict[self.rodkey]
        with h5py.File(self.filename,'a') as db:
            group = db[self.rodkey][self.slicekey]['attrs']
            if key in group.keys():
                return BINoculars.space.get_axis_values(axes, self.axis, self.resolution), numpy.ma.array(group[key], mask = numpy.array(group[mkey]))
                 
    def load_loc(self, index):
        loc = list()   
        with h5py.File(self.filename,'a') as db:
             count = itertools.count()
             key = 'guessloc{0}'.format(count.next())
             while self.load_sliceattr(index, key) != None:
                 loc.append(self.load_sliceattr(index, key))
                 key = 'guessloc{0}'.format(count.next())
             if len(loc) > 0:
                 return loc
             else:
                 count = itertools.count()
                 key = 'loc{0}'.format(count.next())
                 while self.load_sliceattr(index, key) != None:
                     loc.append(self.load_sliceattr(index, key))
                     key = 'loc{0}'.format(count.next())
                 if len(loc) > 0:
                     return loc
                 else:
                     return None

    def save_loc(self, index, loc):
        for i, value in enumerate(loc):
            self.save_sliceattr(index, 'guessloc{0}'.format(i), value) 

    def __iter__(self):
        for index in range(self.rodlength()):
            yield self.space_from_index(index)

def short_filename(filename):
    return filename.split('/')[-1].split('.')[0]

class HiddenToolbar(NavigationToolbar2QTAgg):
    def __init__(self, corner_callback, canvas):
        NavigationToolbar2QTAgg.__init__(self, canvas, None)
        self._corner_callback = corner_callback
        self.zoom()

    def press(self, event):
        self._corner_preclick = self._views()
        
    def release(self, event):
        if self._corner_preclick == self._views():
            self._corner_callback(event.xdata, event.ydata)
        self._corner_preclick = None
                
class FitWidget(QtGui.QWidget):
    def __init__(self, database ,parent=None):
        super(FitWidget, self).__init__(parent)

        self.database = database
        vbox = QtGui.QHBoxLayout() 

        self.figure = matplotlib.figure.Figure()
        self.canvas = FigureCanvasQTAgg(self.figure)
        self.toolbar = HiddenToolbar(self.loc_callback, self.canvas)

        vbox.addWidget(self.canvas)
        self.setLayout(vbox)

    def loc_callback(self, x, y):
        if self.ax:
            self.database.save_loc(self.currentindex(), numpy.array([x, y]))
            
    def plot(self, index = None):
        if index == None:
            index = self.currentindex()
        space = self.database.space_from_index(index)
        fitdata = self.database.load_data(index, 'fit')
        self.figure.clear()
        self.figure.space_axes = space.axes
        info = self.database.get_index_value(index)
        label = self.database.axis

        if fitdata is not None:
            if space.dimension == 1:
                self.ax = self.figure.add_subplot(111)
                BINoculars.plot.plot(space, self.figure, self.ax, fit = fitdata)
            elif space.dimension == 2:
                self.ax = self.figure.add_subplot(121)
                BINoculars.plot.plot(space, self.figure, self.ax, fit = None)
                self.ax = self.figure.add_subplot(122)
                BINoculars.plot.plot(space, self.figure, self.ax, fit = fitdata)
        else:
            self.ax = self.figure.add_subplot(111)
            BINoculars.plot.plot(space, self.figure, self.ax)
        self.figure.suptitle('{0}, res = {1}, {2} = {3}'.format(self.database.rodkey, self.database.resolution, label, info))
        self.canvas.draw()

    def fit(self, index, space, function):
        print index
        if not len(space.get_masked().compressed()) == 0:
            loc = self.database.load_loc(index)
            if loc:
                if loc == list(float(0) for i in loc):
                    loc = None
            fit = function(space, loc = loc)
            fit.fitdata.mask = space.get_masked().mask
            self.database.save_data(index, 'fit',  fit.fitdata)
            params = list(line.split(':')[0] for line in fit.summary.split('\n'))
            print fit.result, fit.variance
            for key, value in zip(params, fit.result):
                self.database.save_sliceattr(index, key, value)
            for key, value in zip(params, fit.variance):
                self.database.save_sliceattr(index, 'var_{0}'.format(key), value)

    def currentindex(self):
        index = self.database.load('index')
        if index == None:
            return 0
        else:
            return index

class IntegrateWidget(QtGui.QWidget):
    def __init__(self, database, parent = None):
        super(IntegrateWidget, self).__init__(parent)
        self.database = database

        self.figure = matplotlib.figure.Figure()
        self.canvas = FigureCanvasQTAgg(self.figure)
        self.toolbar = HiddenToolbar(self.loc_callback, self.canvas)

        hbox = QtGui.QHBoxLayout() 

        splitter = QtGui.QSplitter(QtCore.Qt.Vertical)
        self.make_controlwidget()

        splitter.addWidget(self.canvas)
        splitter.addWidget(self.control_widget)

        hbox.addWidget(splitter) 
        self.setLayout(hbox)  

    def make_controlwidget(self):
        self.control_widget = QtGui.QWidget()

        integratebox = QtGui.QVBoxLayout()
        intensitybox = QtGui.QHBoxLayout()
        backgroundbox = QtGui.QHBoxLayout()

        self.tracker = QtGui.QCheckBox('peak tracker')
        self.tracker.setChecked(1)
        self.locx = QtGui.QDoubleSpinBox()
        self.locy = QtGui.QDoubleSpinBox()
        self.locx.setDisabled(True)
        self.locy.setDisabled(True)
        self.tracker.clicked.connect(self.refresh_tracker)

        self.aroundroi = QtGui.QCheckBox('background around roi')
        self.aroundroi.setChecked(1)
        self.aroundroi.clicked.connect(self.refresh_aroundroi)

        self.hsize = QtGui.QDoubleSpinBox()
        self.vsize = QtGui.QDoubleSpinBox()

        intensitybox.addWidget(QtGui.QLabel('roi size:'))
        intensitybox.addWidget(self.hsize)
        intensitybox.addWidget(self.vsize)

        self.left = QtGui.QDoubleSpinBox()
        self.right = QtGui.QDoubleSpinBox()
        self.top = QtGui.QDoubleSpinBox()
        self.bottom = QtGui.QDoubleSpinBox()

        QtCore.QObject.connect(self.hsize, QtCore.SIGNAL("valueChanged(double)"), self.send)
        QtCore.QObject.connect(self.vsize, QtCore.SIGNAL("valueChanged(double)"), self.send)
        QtCore.QObject.connect(self.left, QtCore.SIGNAL("valueChanged(double)"), self.send)
        QtCore.QObject.connect(self.right, QtCore.SIGNAL("valueChanged(double)"), self.send)
        QtCore.QObject.connect(self.top, QtCore.SIGNAL("valueChanged(double)"), self.send)
        QtCore.QObject.connect(self.bottom, QtCore.SIGNAL("valueChanged(double)"), self.send)

        backgroundbox.addWidget(self.aroundroi)
        backgroundbox.addWidget(self.left)
        backgroundbox.addWidget(self.right)
        backgroundbox.addWidget(self.top)
        backgroundbox.addWidget(self.bottom)
                
        integratebox.addLayout(intensitybox)
        integratebox.addLayout(backgroundbox)

        minibox = QtGui.QHBoxLayout()
        minibox.addWidget(self.tracker)
        minibox.addWidget(self.locx)
        minibox.addWidget(self.locy)
        integratebox.addLayout(minibox)
       
        self.control_widget.setLayout(integratebox)

    def refresh_aroundroi(self):
        self.database.save('aroundroi', self.aroundroi.checkState())
        axes = self.database.paxes()
        if not self.aroundroi.checkState():
            self.left.setMinimum(axes[0].min)
            self.left.setMaximum(axes[0].max)
            self.right.setMinimum(axes[0].min)
            self.right.setMaximum(axes[0].max)
            self.top.setMinimum(axes[1].min)
            self.top.setMaximum(axes[1].max)
            self.bottom.setMinimum(axes[1].min)
            self.bottom.setMaximum(axes[1].max)
        else:
            self.left.setMinimum(0)
            self.left.setMaximum(axes[0].max - axes[0].min)
            self.right.setMinimum(0)
            self.right.setMaximum(axes[0].max - axes[0].min)
            self.top.setMinimum(0)
            self.top.setMaximum(axes[1].max - axes[1].min)
            self.bottom.setMinimum(0)
            self.bottom.setMaximum(axes[1].max - axes[1].min)

    def refresh_tracker(self):
        self.database.save('tracker', self.tracker.checkState())
        if self.tracker.checkState():
            self.locx.setDisabled(True)
            self.locy.setDisabled(True)
        else:
            self.locx.setDisabled(False)
            self.locy.setDisabled(False)
        self.plot_box()

    def set_axis(self):
        roi = self.database.load('roi')

        aroundroi = self.database.load('aroundroi')
        if aroundroi != None:
            self.aroundroi.setChecked(aroundroi)
        else:
            self.aroundroi.setChecked(True)
        self.refresh_aroundroi()

        axes = self.database.paxes()    

        self.hsize.setSingleStep(axes[1].res)
        self.hsize.setDecimals(len(str(axes[1].res)) - 2)
        self.vsize.setSingleStep(axes[0].res)
        self.vsize.setDecimals(len(str(axes[0].res)) - 2)
        self.left.setSingleStep(axes[1].res)
        self.left.setDecimals(len(str(axes[1].res)) - 2)
        self.right.setSingleStep(axes[1].res)
        self.right.setDecimals(len(str(axes[1].res)) - 2)
        self.top.setSingleStep(axes[0].res)
        self.top.setDecimals(len(str(axes[0].res)) - 2)
        self.bottom.setSingleStep(axes[0].res)
        self.bottom.setDecimals(len(str(axes[0].res)) - 2)

        self.locx.setSingleStep(axes[0].res)
        self.locx.setDecimals(len(str(axes[0].res)) - 2)
        self.locx.setMinimum(axes[0].min)
        self.locx.setMaximum(axes[0].max)

        self.locy.setSingleStep(axes[1].res)
        self.locy.setDecimals(len(str(axes[1].res)) - 2)
        self.locy.setMinimum(axes[1].min)
        self.locy.setMaximum(axes[1].max)

        tracker = self.database.load('tracker')
        if tracker != None:
            self.tracker.setChecked(tracker)
        else:
            self.tracker.setChecked(True)

        if roi is not None:
             for box, value in zip([self.hsize, self.vsize, self.left, self.right, self.top, self.bottom], roi):
                box.setValue(value)

        if self.fixed_loc() != None:
            x,y = self.fixed_loc()
            self.locx.setValue(x)
            self.locy.setValue(y)

    def send(self):
        roi = [self.hsize.value(), self.vsize.value(), self.left.value() ,self.right.value() ,self.top.value(), self.bottom.value()]
        self.database.save('roi', roi)
        self.plot_box()

    def integrate(self, index, space):
        if self.tracker.checkState():
            loc = self.database.load_loc(index)
        else:
            loc = self.fixed_loc()

        if loc != None:
            axes = space.axes

            key = space.get_key(self.intkey(loc, axes))

            fitdata = self.database.load_data(index, 'fit')
            if fitdata != None:
                fitintensity = fitdata[key].data.flatten()
                fitbkg = numpy.hstack(fitdata[space.get_key(bkgkey)].data.flatten() for bkgkey in self.bkgkeys(loc, axes))
                if numpy.alen(fitbkg) == 0:
                    fitstructurefactor = fitintensity.sum()
                elif numpy.alen(fitintensity) == 0:
                    fitstructurefactor = numpy.nan
                else:
                    fitstructurefactor = numpy.sqrt(fitintensity.sum() - numpy.alen(fitintensity) * 1.0 / numpy.alen(fitbkg) * fitbkg.sum())
                self.database.save_sliceattr(index, 'fitsf', fitstructurefactor)
                
            niintensity = space[self.intkey(loc, axes)].get_masked().compressed()
            
            try:
                intensity = interpolate(space[self.intkey(loc, axes)]).flatten()
                bkg = numpy.hstack(space[bkgkey].get_masked().compressed() for bkgkey in self.bkgkeys(loc, axes))
                interdata = space.get_masked()
                interdata[key] = intensity.reshape(interdata[key].shape)
                interdata[key].mask = numpy.zeros_like(interdata[key])
                self.database.save_data(index, 'inter',  interdata)
            except Exception as e:
                print 'Warning error interpolating slice {0}: {1}'.format(index, e.message)
                intensity = numpy.array([])
                bkg = numpy.array([])

            if numpy.alen(intensity) == 0:
                structurefactor = numpy.nan
                nistructurefactor = numpy.nan
            elif numpy.alen(bkg) == 0:
                structurefactor = numpy.sqrt(intensity.sum())
                nistructurefactor = numpy.sqrt(niintensity.sum())
            else:
                structurefactor = numpy.sqrt(intensity.sum() - numpy.alen(intensity) * 1.0 / numpy.alen(bkg) * bkg.sum())
                nistructurefactor = numpy.sqrt(niintensity.sum() - numpy.alen(niintensity) * 1.0 / numpy.alen(bkg) * bkg.sum())

            self.database.save_sliceattr(index, 'sf', structurefactor)
            self.database.save_sliceattr(index, 'nisf', nistructurefactor)

            print 'Structurefactor {0}: {1}'.format(index, structurefactor)

    def intkey(self, coords, axes):

        vsize = self.vsize.value() / 2
        hsize = self.hsize.value() / 2
        return tuple(ax.restrict(slice(coord - size, coord + size)) for ax, coord, size in zip(axes, coords, [vsize, hsize]))

    def bkgkeys(self, coords, axes):
        aroundroi = self.database.load('aroundroi')
        if aroundroi:
            key = self.intkey(coords, axes)

            vsize = self.vsize.value() / 2
            hsize = self.hsize.value() / 2

            leftkey = (key[0], axes[1].restrict(slice(coords[1] - hsize - self.left.value(), coords[1] - hsize)))
            rightkey = (key[0], axes[1].restrict(slice(coords[1] + hsize, coords[1] + hsize + self.right.value())))
            topkey = (axes[0].restrict(slice(coords[0] - vsize - self.top.value(), coords[0] - vsize)), key[1])
            bottomkey =  (axes[0].restrict(slice(coords[0] + vsize, coords[0] + vsize  + self.bottom.value())), key[1])

            return leftkey, rightkey, topkey, bottomkey
        else:
            return [(axes[0].restrict(slice(self.left.value(), self.right.value())), axes[1].restrict(slice(self.top.value(), self.bottom.value())))]

    def fixed_loc(self):
        x = self.database.load('fixed_locx')
        y = self.database.load('fixed_locy')

        if x != None and y != None:
            return numpy.array([x, y])
        else:
            return None

    def loc_callback(self, x, y):
        if self.ax:
            self.database.save_loc(self.currentindex(), numpy.array([x, y]))
            if not self.tracker.checkState():
                self.database.save('fixed_locx', x)
                self.database.save('fixed_locy', y)
                self.locx.setValue(x)
                self.locy.setValue(y)
            self.plot_box()

    def plot(self, index = None):
        if index == None:
            index = self.currentindex()
        space = self.database.space_from_index(index)
        interdata = self.database.load_data(index, 'inter')
        info = self.database.get_index_value(index)
        label = self.database.axis

        self.figure.clear()
        self.figure.space_axes = space.axes

        if interdata is not None:
            if space.dimension == 1:
                self.ax = self.figure.add_subplot(111)
                BINoculars.plot.plot(space, self.figure, self.ax, fit = interdata)
            elif space.dimension == 2:
                self.ax = self.figure.add_subplot(121)
                BINoculars.plot.plot(space, self.figure, self.ax, fit = None)
                self.ax = self.figure.add_subplot(122)
                BINoculars.plot.plot(space, self.figure, self.ax, fit = interdata)
        else:
            self.ax = self.figure.add_subplot(111)
            BINoculars.plot.plot(space, self.figure, self.ax)

        self.figure.suptitle('{0}, res = {1}, {2} = {3}'.format(self.database.rodkey, self.database.resolution, label, info))

        self.plot_box()
        self.canvas.draw()

    def plot_box(self):
        if not self.tracker.checkState():
            loc = self.fixed_loc()
        else:
            loc = self.database.load_loc(self.currentindex())
        if len(self.figure.get_axes()) != 0 and loc != None: 
            ax = self.figure.get_axes()[0]
            axes = self.figure.space_axes
            key = self.intkey(loc, axes)
            bkgkey = self.bkgkeys(loc, axes)
            ax.patches = []
            rect = Rectangle((key[0].start, key[1].start), key[0].stop - key[0].start, key[1].stop - key[1].start, alpha = 0.2,color =  'k')
            ax.add_patch(rect)
            for k in bkgkey:
                bkg = Rectangle((k[0].start, k[1].start), k[0].stop - k[0].start, k[1].stop - k[1].start, alpha = 0.2,color =  'r')
                ax.add_patch(bkg)
            self.canvas.draw()

    def currentindex(self):
        index = self.database.load('index')
        if index == None:
            return 0
        else:
            return index

class ButtonedSlider(QtGui.QWidget):
    def __init__(self,parent=None):
        super(ButtonedSlider, self).__init__(parent)

        self.navigation_button_left_end = QtGui.QPushButton('|<')
        self.navigation_button_left_one = QtGui.QPushButton('<')
        self.navigation_slider = QtGui.QSlider(Qt.Qt.Horizontal)
        self.navigation_slider.sliderReleased.connect(self.send)

        self.navigation_button_right_one = QtGui.QPushButton('>')
        self.navigation_button_right_end = QtGui.QPushButton('>|')

        self.navigation_button_left_end.setMaximumWidth(20)
        self.navigation_button_left_one.setMaximumWidth(20)
        self.navigation_button_right_end.setMaximumWidth(20)
        self.navigation_button_right_one.setMaximumWidth(20)

        self.navigation_button_left_end.clicked.connect(self.slider_change_left_end)
        self.navigation_button_left_one.clicked.connect(self.slider_change_left_one)
        self.navigation_button_right_end.clicked.connect(self.slider_change_right_end)
        self.navigation_button_right_one.clicked.connect(self.slider_change_right_one)

        box = QtGui.QHBoxLayout() 
        box.addWidget(self.navigation_button_left_end)
        box.addWidget(self.navigation_button_left_one)
        box.addWidget(self.navigation_slider)
        box.addWidget(self.navigation_button_right_one)
        box.addWidget(self.navigation_button_right_end)

        self.setDisabled(True)
        self.setLayout(box)

    def set_length(self,length):
        self.navigation_slider.setMinimum(0)
        self.navigation_slider.setMaximum(length - 1)
        self.navigation_slider.setTickPosition(QtGui.QSlider.TicksBelow)
        self.navigation_slider.setValue(0)
        self.setEnabled(True)


    def send(self):
        self.emit(QtCore.SIGNAL('slice_index'), self.navigation_slider.value())

    def slider_change_left_one(self):
        self.navigation_slider.setValue(max(self.navigation_slider.value() - 1, 0))
        self.send()

    def slider_change_left_end(self):
        self.navigation_slider.setValue(0)
        self.send()

    def slider_change_right_one(self):
        self.navigation_slider.setValue(min(self.navigation_slider.value() + 1, self.navigation_slider.maximum()))
        self.send()

    def slider_change_right_end(self):
        self.navigation_slider.setValue(self.navigation_slider.maximum())
        self.send()

    def index(self):
        return self.navigation_slider.value()

    def set_index(self, index):
        self.navigation_slider.setValue(index)

class HiddenToolbar2(NavigationToolbar2QTAgg):
    def __init__(self, canvas):
        NavigationToolbar2QTAgg.__init__(self, canvas, None)
        self.zoom()

class OverviewWidget(QtGui.QWidget):
    def __init__(self, database, parent = None):
        super(OverviewWidget, self).__init__(parent)

        self.databaselist = list()

        self.figure = matplotlib.figure.Figure()
        self.canvas = FigureCanvasQTAgg(self.figure)
        self.toolbar = HiddenToolbar2(self.canvas)

        self.table = QtGui.QTableWidget(0,2)
        self.make_table()

        self.table.cellClicked.connect(self.plot)

        hbox = QtGui.QHBoxLayout() 

        splitter = QtGui.QSplitter(QtCore.Qt.Horizontal)

        splitter.addWidget(self.canvas)
        splitter.addWidget(self.control_widget)

        hbox.addWidget(splitter) 
        self.setLayout(hbox)  

    def select(self):
        selection = []
        for index in range(self.table.rowCount()):
            checkbox = self.table.cellWidget(index, 0)
            if checkbox.checkState():
                selection.append(str(self.table.cellWidget(index,1).text()))
        return selection


    def make_table(self):
        self.control_widget = QtGui.QWidget()
        vbox = QtGui.QVBoxLayout()
        minibox = QtGui.QHBoxLayout()

        vbox.addWidget(self.table)
        self.table.setHorizontalHeaderLabels(['','param'])
        for index, width in enumerate([25,50]):
            self.table.setColumnWidth(index, width)
        self.log = QtGui.QCheckBox('log')
        self.log.clicked.connect(self.plot)
        self.export_button = QtGui.QPushButton('export curves')

        self.export_button.clicked.connect(self.export)

        minibox.addWidget(self.log)
        minibox.addWidget(self.export_button)
        vbox.addLayout(minibox)
        self.control_widget.setLayout(vbox) 

    def export(self):
        folder =  str(QtGui.QFileDialog.getExistingDirectory(self, "Select directory to save curves"))
        params = self.select()
        for param in params:
            for database in self.databaselist:
                x, y = database.all_from_key(param)
                args = numpy.argsort(x)
                numpy.savetxt( os.path.join(folder,'{0}_{1}.txt'.format(param, database.rodkey)), numpy.vstack(arr[args] for arr in [x, y]).T)

    def refresh(self, databaselist):
        self.databaselist = databaselist
        params = self.select()
        while self.table.rowCount() > 0:
            self.table.removeRow(0)

        allparams = list(list(param for param in database.all_attrkeys() if not param.startswith('mask')) for database in databaselist)
        if len(allparams) > 0:
            uniqueparams = numpy.unique(numpy.hstack(params for params in allparams))
        else:
            uniqueparams = []

        for param in uniqueparams:
            index = self.table.rowCount()
            self.table.insertRow(index)

            checkboxwidget = QtGui.QCheckBox()
            if param in params:
                checkboxwidget.setChecked(1)
            else:
                checkboxwidget.setChecked(0)
            self.table.setCellWidget(index,0, checkboxwidget)
            checkboxwidget.clicked.connect(self.plot)

            item = QtGui.QLabel(param)
            self.table.setCellWidget(index, 1, item)

        self.plot()

    def plot(self):
        params = self.select()
        self.figure.clear()

        self.ax = self.figure.add_subplot(111)
        for param in params:
            for database in self.databaselist:
                x, y = database.all_from_key(param)
                self.ax.plot(x, y, '+', label = '{0} - {1}'.format(param, database.rodkey))
        self.ax.legend()    
        if self.log.checkState():
            self.ax.semilogy()
        self.canvas.draw()

def interpolate(space):
    data = space.get_masked()
    mask = data.mask
    grid = numpy.vstack(numpy.ma.array(g, mask=mask).compressed() for g in space.get_grid()).T
    open = numpy.vstack(numpy.ma.array(g, mask=numpy.invert(mask)).compressed() for g in space.get_grid()).T
    if open.shape[0] == 0:
        return data.compressed()
    elif grid.shape[0] == 0:
        return data.compressed()
    else:
        interpolated = griddata(grid, data.compressed(), open)            
        values = data.data.copy()
        values[mask] = interpolated
        mask = numpy.isnan(values)
        if mask.sum() > 0:
            data = numpy.ma.array(values, mask = mask)
            grid = numpy.vstack(numpy.ma.array(g, mask=mask).compressed() for g in space.get_grid()).T
            open = numpy.vstack(numpy.ma.array(g, mask=numpy.invert(mask)).compressed() for g in space.get_grid()).T
            interpolated = griddata(grid, data.compressed(), open, method = 'nearest')
            values[mask] = interpolated
        return values

def find_unused_rodkey(rodkey, rods):
    if not rodkey in rods:
        return rodkey
    for index in itertools.count(0):
        newkey = '{0}_{1}'.format(rodkey, index)
        if newkey not in rods:
            return newkey

if __name__ == "__main__":
    app = QtGui.QApplication(sys.argv)

    main = Window()
    main.resize(1000, 600)
    main.show()

    
    sys.exit(app.exec_())







  

