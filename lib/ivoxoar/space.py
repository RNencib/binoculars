# Written by Willem Onderwaater and Sander Roobol as part of a collaboration
# between the ID03 beamline at the European Synchrotron Radiation Facility and
# the Interface Physics group at Leiden University.

import sys
import os
import itertools
import random
import cPickle as pickle
import gzip
import numbers
import numpy
import inspect


# handle old zpi's from before ivoxoar's major restructuring
def _pickle_translate(module, name):
    if module == '__main__' and name in ('Space', 'Axis'):
        return 'ivoxoar.space', name
    return module, name

if inspect.isbuiltin(pickle.Unpickler):
    # real cPickle: cannot subclass
    def _find_global(module, name):
        module, name = _pickle_translate(module, name)
        __import__(module)
        return getattr(sys.modules[module], name)

    def pickle_load(fileobj):
        unpickler = pickle.Unpickler(fileobj)
        unpickler.find_global = _find_global
        return unpickler.load()
else:
    # pure python implementation
    class _Unpickler(pickle.Unpickler):
        def find_class(self, module, name):
            module, name = _pickle_translate(module, name)
            return pickle.Unpickler.find_class(self, module, name)

    def pickle_load(fileobj):
        unpickler = _Unpickler(fileobj)
        return unpickler.load()


def sum_onto(a, axis):
    for i in reversed(range(len(a.shape))):
        if axis != i:
            a = a.sum(axis=i)
    return a


class Axis(object):
    def __init__(self, min, max, res, label=None):
        self.res = float(res)
        if round(min / self.res) != round(min / self.res,6) or round(max / self.res) != round(max / self.res,6):
            self.min = numpy.floor(float(min)/self.res)*self.res
            self.max = numpy.ceil(float(max)/self.res)*self.res
        else:
            self.min = min
            self.max = max
        self.label = label
    
    def __len__(self):
        return int(round((self.max - self.min) / self.res)) + 1

    def __getitem__(self, key):
        if isinstance(key, slice):
            if key.step is not None:
                raise IndexError('stride not supported')
            if key.start is None:
                start = 0
            elif isinstance(key.start, int):
                start = key.start
            else:
                raise IndexError('key start must be integer')
            if key.stop is None:
                stop = len(self)
            elif isinstance(key.stop, int):
                stop = key.stop
            else:
                raise IndexError('slice stop must be integer')
            return self.__class__(self.min + start * self.res, self.min + (stop - 1) * self.res, self.res, self.label)
        elif isinstance(key, int):
            if key >= len(self):  # to support iteration
                raise IndexError('key out of range')
            return self.min + key * self.res
        else:
            raise IndexError('unknown key {0!r}'.format(key))

    def get_index(self, value):
        if isinstance(value, numbers.Number):
            if self.min <= value <= self.max:
                return int(round((value - self.min) / self.res))
            raise ValueError('cannot get index: value {0} not in range [{1}, {2}]'.format(value, self.min, self.max))
        else:
            if ((self.min <= value) & (value <= self.max)).all():
                return numpy.around((value - self.min) / self.res).astype(int)
            raise ValueError('cannot get indices, values from [{0}, {1}], axes range [{2}, {3}]'.format(value.min(), value.max(), self.min, self.max))

    def __or__(self, other): # union operation
        if not isinstance(other, Axis):
            return NotImplemented
        if not self.is_compatible(other):
            raise ValueError('cannot unite axes with different resolution/label')
        return self.__class__(min(self.min, other.min), max(self.max, other.max), self.res, self.label)

    def __eq__(self, other):
        if not isinstance(other, Axis):
            return NotImplemented
        return self.res == other.res and self.min == other.min and self.max == other.max and self.label == other.label

    def __hash__(self):
        return hash(self.min) ^ hash(self.max) ^ hash(self.res) ^ hash(self.label)

    def is_compatible(self, other):
        if not isinstance(other, Axis):
            return False
        return self.res == other.res and self.label == other.label

    def __contains__(self, other):
        if isinstance(other, numbers.Number):
            return self.min <= other <= self.max
        elif isinstance(other, Axis):
            return self.is_compatible(other) and self.min <= other.min and self.max >= other.max

    def rebound(self, min, max):
        return self.__class__(min, max, self.res, self.label)

    def rebin(self, factor):
        newres = self.res*factor
        left = int(round(self.min/self.res))
        right = int(round(self.max/self.res))
        new = self.__class__(newres * numpy.floor(round(self.min / newres, 3)), newres * numpy.ceil(round(self.max / newres, 3)), newres, self.label)
        return left % factor, -right % factor, new

    def __repr__(self):
        return '{0.__class__.__name__} {0.label} (min={0.min}, max={0.max}, res={0.res}, count={1})'.format(self, len(self))


class EmptySpace(object):
    def __iadd__(self, other):
        if not isinstance(other, Space):
            return NotImplemented
        return other


class Space(object):
    def __init__(self, axes):
        if len(axes) > 1 and any(axis.label is None for axis in axes):
            raise ValueError('axis label is required for multidimensional space')
        self.axes = tuple(axes)
        
        self.photons = numpy.zeros([len(ax) for ax in self.axes], order='C')
        self.contributions = numpy.zeros(self.photons.shape, dtype=numpy.uint32, order='C')

    @property
    def dimension(self):
        return len(self.axes)

    def copy(self):
        new = self.__class__(self.axes)
        new.photons[:] = self.photons
        new.contributions[:] = self.contributions
        return new

    def get(self):
        return self.photons/self.contributions

    def __repr__(self):
        return '{0.__class__.__name__} \n{1}'.format(self, '\n'.join(repr(ax) for ax in self.axes))
    
    def __getitem__(self, key):
        if isinstance(key, numbers.Number) or isinstance(key, slice):
            if not len(self.axes) == 1:
                raise IndexError('dimension mismatch')
            else:
                key = [key]
        elif not isinstance(key, tuple) or not len(key) == len(self.axes):
            raise IndexError('dimension mismatch')

        newkey = tuple(self._convertindex(k,ax) for k, ax in zip(key, self.axes))
        newaxes = tuple(ax[k] for k, ax in zip(newkey, self.axes) if isinstance(ax[k], Axis))
        if not newaxes:
            raise ValueError('zero-dimensional spaces are not supported')
        newspace = self.__class__(newaxes)
        newspace.photons = self.photons[newkey]
        newspace.contributions = self.contributions[newkey]
        return newspace

    def _convertindex(self,key,ax):
        if isinstance(key,slice):
            if key.step is not None:
                raise IndexError('stride not supported')
            if key.start is None:
                start = None
            else:
                start = ax.get_index(key.start)
            if key.stop is None:
                stop = None
            else:
                stop = ax.get_index(key.stop)
            return slice(start, stop)
        if isinstance(key, numbers.Number):
            return ax.get_index(key)
        raise TypeError('unrecognized slice')

    def project(self, axis):
        if isinstance(axis, Axis):
            index = self.axes.index(axis)
        elif isinstance(axis, basestring):
            index = self.get_axindex_by_label(axis)
        elif isinstance(axis, int):
            index = axis
        else:
            raise ValueError('unknown axis specification {0!r}'.format(axis))
        newaxes = list(self.axes)
        newaxes.pop(index)
        newspace = self.__class__(newaxes)
        newspace.photons = self.photons.sum(axis=index)
        newspace.contributions = self.contributions.sum(axis=index)
        return newspace

    def slice(self, axis, key):
        if isinstance(axis, Axis):
            axindex = self.axes.index(axis)
        elif isinstance(axis, basestring):
            axindex = self.get_axindex_by_label(axis)
        elif isinstance(axis, int):
            axindex = axis
        else:
            raise ValueError('unknown axis specification {0!r}'.format(axis))
        newkey = list(slice(None) for ax in self.axes)
        newkey[axindex] = key
        return self.__getitem__(tuple(newkey))

    def get_axindex_by_label(self, label):
        label = label.lower()
        matches = tuple(i for i, axis in enumerate(self.axes) if axis.label.lower() == label)
        if len(matches) == 0:
            raise ValueError('no matching axis found')
        elif len(matches) == 1:
            return matches[0]
        else:
            raise ValueError('ambiguous axis label {0}'.format(label))

    def get_masked(self):
        return numpy.ma.array(data=self.get(), mask=(self.contributions == 0))
        
    def get_grid(self):
        mask = self.get_masked().mask
        igrid = numpy.mgrid[list(slice(0,len(ax)) for ax in self.axes)]
        grid = tuple(numpy.ma.array(igrid[i,...] * ax.res + ax.min, mask = mask) for i,ax in zip(range(igrid.shape[0]),self.axes) )
        return grid

    def __add__(self, other):
        if not isinstance(other, Space):
            return NotImplemented
        if not len(self.axes) == len(other.axes) or not all(a.is_compatible(b) for (a, b) in zip(self.axes, other.axes)):
            raise ValueError('cannot add spaces with different dimensionality or resolution')

        new = self.__class__([a | b for (a, b) in zip(self.axes, other.axes)])
        new += self
        new += other
        return new

    def __iadd__(self, other):
        if not isinstance(other, Space):
            return NotImplemented
        if not len(self.axes) == len(other.axes) or not all(a.is_compatible(b) for (a, b) in zip(self.axes, other.axes)):
            raise ValueError('cannot add spaces with different dimensionality or resolution')

        if not all(other_ax in self_ax for (self_ax, other_ax) in zip(self.axes, other.axes)):
            return self.__add__(other)

        index = tuple(slice(self_ax.get_index(other_ax.min), self_ax.get_index(other_ax.min) + len(other_ax)) for (self_ax, other_ax) in zip(self.axes, other.axes))
        self.photons[index] += other.photons
        self.contributions[index] += other.contributions
        return self

    def __sub__(self, other):
        if not isinstance(other, Space):
            return NotImplemented
        if self.axes != other.axes or not (self.contributions == other.contributions).all():
            # FIXME: be a bit more helpful if all axes are compatible
            raise ValueError('cannot subtract spaces that are not identical (axes + contributions)')
        new = self.copy()
        new.photons -= other.photons # don't call __isub__ here because the compatibility check is labourous
        return new

    def __isub__(self, other):
        if not isinstance(other, Space):
            return NotImplemented
        if self.axes != other.axes or not (self.contributions == other.contributions).all():
             print self.axes
             print other.axes
             raise ValueError('cannot subtract spaces that are not identical (axes + contributions)')
        self.photons -= other.photons
        return self

    def trim(self):
        mask = self.contributions > 0
        lims = (numpy.flatnonzero(sum_onto(mask, i)) for (i, ax) in enumerate(self.axes))
        lims = tuple((i.min(), i.max()) for i in lims)
        self.axes = tuple(ax.rebound(ax[min], ax[max]) for (ax, (min, max)) in zip(self.axes, lims))
        slices = tuple(slice(min, max+1) for (min, max) in lims)
        self.photons = self.photons[slices].copy()
        self.contributions = self.contributions[slices].copy()

    def rebin(self, factors):
        if len(factors) != len(self.axes):
            raise ValueError('dimension mismatch between factors and axes')
        if not all(isinstance(factor, int) for factor in factors) or not all(factor % 2 == 0 for factor in factors):
            raise ValueError('binning factors must be even integers')

        lefts, rights, newaxes = zip(*[ax.rebin(factor) for ax, factor in zip(self.axes, factors)])
        tempshape = tuple(size + left + right + factor for size, left, right, factor in zip(self.photons.shape, lefts, rights, factors))

        photons = numpy.zeros(tempshape, order='C')
        contributions = numpy.zeros(tempshape, dtype=numpy.uint32, order='C')
        pad = tuple(slice(left+factor/2, left+factor/2+size) for left, factor, size in zip(lefts, factors, self.photons.shape))
        photons[pad] = self.photons
        contributions[pad] = self.contributions

        new = self.__class__(newaxes)
        for offsets in itertools.product(*[range(factor) for factor in factors]):
            stride = tuple(slice(offset, offset+size+left+factor/2, factor) for offset, size, factor, left in zip(offsets, self.photons.shape, factors, lefts))
            new.photons += photons[stride]
            new.contributions += contributions[stride]

        return new
    
    def process_image(self, coordinates, intensity):
        # note: coordinates must be tuple of arrays, not a 2D array
        if len(coordinates) != len(self.axes):
            raise ValueError('dimension mismatch between coordinates and axes')

        valid = numpy.isfinite(intensity)
        intensity = intensity[valid]
        if not intensity.size:
            return
        coordinates = tuple(coord[valid] for coord in coordinates)

        indices = numpy.array(tuple(ax.get_index(coord) for (ax, coord) in zip(self.axes, coordinates)))
        for i in range(0, len(self.axes)):
            for j in range(i+1, len(self.axes)):
                indices[i,:] *= len(self.axes[j])
        indices = indices.sum(axis=0).astype(int)
        photons = numpy.bincount(indices, weights=intensity)
        contributions = numpy.bincount(indices)
    
        self.photons.ravel()[:photons.size] += photons
        self.contributions.ravel()[:contributions.size] += contributions

    def tofile(self, filename):
        tmpfile = '{0}-{1:x}.tmp'.format(os.path.splitext(filename)[0], random.randint(0, 2**32-1))
        fp = gzip.open(tmpfile, 'wb')
        try:
            pickle.dump(self, fp, pickle.HIGHEST_PROTOCOL)
        finally:
            fp.close()
        os.rename(tmpfile, filename)
    
    @classmethod
    def fromfile(cls, filename):
        fp = gzip.open(filename,'rb')
        try:
            return pickle_load(fp)
        finally:
            fp.close()
