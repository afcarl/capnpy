# glossary:
#
#   - size: they are always expressed in WORDS
#   - length: they are always expressed in BYTES


import struct
import capnpy
from capnpy.ptr import Ptr, StructPtr, ListPtr, FarPtr
from capnpy.type import Types
from capnpy.printer import BufferPrinter

class Blob(object):
    """
    Base class to read a generic capnp object.
    """

    def __new__(self):
        raise NotImplementedError('Cannot instantiate Blob directly; '
                                  'use Blob.from_buffer instead')

    @classmethod
    def from_buffer(cls, buf, offset, segment_offsets):
        self = object.__new__(cls)
        self._buf = buf
        self._offset = offset
        assert self._offset < len(self._buf)
        self._segment_offsets = segment_offsets
        return self

    def _read_primitive(self, offset, t):
        return struct.unpack_from('<' + t.fmt, self._buf, self._offset+offset)[0]

    def _read_bit(self, offset, bitmask):
        val = self._read_primitive(offset, Types.uint8)
        return bool(val & bitmask)

    def _read_enum(self, offset, enumtype):
        val = self._read_primitive(offset, Types.int16)
        return enumtype(val)

    def _read_struct(self, offset, structcls):
        """
        Read and dereference a struct pointer at the given offset.  It returns an
        instance of ``cls`` pointing to the dereferenced struct.
        """
        struct_offset = self._deref_ptrstruct(offset)
        if struct_offset is None:
            return None
        return structcls.from_buffer(self._buf,
                                     self._offset+struct_offset,
                                     self._segment_offsets)

    def _read_list(self, offset, listcls, item_type):
        offset, size_tag, item_count = self._deref_ptrlist(offset)
        if offset is None:
            return None
        return listcls.from_buffer(self._buf, self._offset+offset,
                                   self._segment_offsets,
                                   size_tag, item_count, item_type)

    def _read_string(self, offset):
        offset, size_tag, item_count = self._deref_ptrlist(offset)
        if offset is None:
            return None
        assert size_tag == ListPtr.SIZE_8
        start = self._offset + offset
        end = start + item_count - 1
        return self._buf[start:end]

    def _read_data(self, offset):
        offset, size_tag, item_count = self._deref_ptrlist(offset)
        if offset is None:
            return None
        assert size_tag == ListPtr.SIZE_8
        start = self._offset + offset
        end = start + item_count
        return self._buf[start:end]

    def _read_ptr(self, offset):
        ptr = self._read_primitive(offset, Types.int64)
        return Ptr(ptr)

    def _read_group(self, groupcls):
        return groupcls.from_buffer(self._buf, self._offset,
                                    self._segment_offsets)

    def _follow_generic_pointer(self, ptr_offset):
        ptr = self._read_ptr(ptr_offset)
        if ptr == 0:
            return None
        ptr = ptr.specialize()
        blob_offet = ptr.deref(ptr_offset)
        if ptr.kind == StructPtr.KIND:
            GenericStruct = capnpy.struct_.GenericStruct
            return GenericStruct.from_buffer_and_size(self._buf,
                                                      self._offset+blob_offet,
                                                      self._segment_offsets,
                                                      ptr.data_size, ptr.ptrs_size)
        elif ptr.kind == ListPtr.KIND:
            List = capnpy.list.List
            return List.from_buffer(self._buf,
                                    self._offset+blob_offet,
                                    self._segment_offsets,
                                    ptr.size_tag,ptr.item_count, Blob)
        else:
            assert False, 'Unkwown pointer kind: %s' % ptr.kind

    def _deref_ptrstruct(self, offset):
        ptr = self._read_ptr(offset)
        if ptr == 0:
            return None
        if ptr.kind == FarPtr.KIND:
            ptr = ptr.specialize()
            offset, ptr = ptr.follow(self)
        #
        assert ptr.kind == StructPtr.KIND
        return ptr.deref(offset)

    def _deref_ptrlist(self, offset):
        """
        Dereference a list pointer at the given offset.  It returns a tuple
        (offset, size_tag, item_count):

        - offset is where the list items start, from the start of the blob
        - size_tag: specifies the size of each element
        - item_count: the total number of elements
        """
        ptr = self._read_ptr(offset)
        if ptr == 0:
            return None, None, None
        if ptr.kind == FarPtr.KIND:
            ptr = ptr.specialize()
            offset, ptr = ptr.follow(self)
        #
        assert ptr.kind == ListPtr.KIND
        ptr = ptr.specialize()
        offset = ptr.deref(offset)
        return offset, ptr.size_tag, ptr.item_count

    def _print_buf(self, start=None, end='auto', **kwds):
        if start is None:
            start = self._offset
        if end == 'auto':
            end = self._get_body_end()
        elif end is None:
            end = len(self._buf)
        p = BufferPrinter(self._buf)
        p.printbuf(start=start, end=end, **kwds)


# make sure that these two modules are imported, they are used by
# _follow_generic_pointer. We need to put them at the end because of circular
# references
import capnpy.struct_
import capnpy.list
