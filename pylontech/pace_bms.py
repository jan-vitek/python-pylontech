import sys
import serial
import construct
import json


class HexToByte(construct.Adapter):
    def _decode(self, obj, context, path) -> bytes:
        hexstr = ''.join([chr(x) for x in obj])
        return bytes.fromhex(hexstr)


class JoinBytes(construct.Adapter):
    def _decode(self, obj, context, path) -> bytes:
        return ''.join([chr(x) for x in obj]).encode()


class DivideBy1000(construct.Adapter):
    def _decode(self, obj, context, path) -> float:
        return obj / 1000


class DivideBy100(construct.Adapter):
    def _decode(self, obj, context, path) -> float:
        return obj / 100


class ToVolt(construct.Adapter):
    def _decode(self, obj, context, path) -> float:
        return obj / 1000

class ToAmp(construct.Adapter):
    def _decode(self, obj, context, path) -> float:
        return obj / 100

class ToCelsius(construct.Adapter):
    def _decode(self, obj, context, path) -> float:
        return obj / 100

class KelvinToCelsius(construct.Adapter):
    def _decode(self, obj, context, path) -> float:
        return (obj - 2730) / 10



class Pylontech:
    pace_analog_fmt = construct.Struct(
        "Address" / construct.Byte,
        "NumberOfCells" / construct.Int8ub,
        "CellVoltages" / construct.Array(construct.this.NumberOfCells, ToVolt(construct.Int16sb)),
        "NumberOfTemperatures" / construct.Int8ub,
        "Temperatures" / construct.Array(construct.this.NumberOfTemperatures, KelvinToCelsius(construct.Int16sb)),
        "Current" / ToAmp(construct.Int16sb),
        "Voltage" / ToVolt(construct.Int16ub),
        "RemainingCapacity" / DivideBy100(construct.Int16ub),
        "_undef1" / construct.Int8ub,
        "TotalCapacity" / DivideBy100(construct.Int16ub),
        "CycleNumber" / construct.Int16ub,
        "DesignCapacity" / DivideBy100(construct.Int16ub),
    )

    def __init__(self, serial_port='/dev/cu.usbserial-FT65F5C4', baudrate=9600):
#        self.s = serial.Serial(serial_port, baudrate, bytesize=8, parity=serial.PARITY_NONE, stopbits=1, timeout=2)
        self.s = serial.serial_for_url("socket://192.168.102.1:5000", timeout=2)


    @staticmethod
    def get_frame_checksum(frame: bytes):
        assert isinstance(frame, bytes)

        sum = 0
        for byte in frame:
            sum += byte
        sum = ~sum
        sum %= 0x10000
        sum += 1
        return sum

    @staticmethod
    def get_info_length(info: bytes) -> int:
        lenid = len(info)
        if lenid == 0:
            return 0

        lenid_sum = (lenid & 0xf) + ((lenid >> 4) & 0xf) + ((lenid >> 8) & 0xf)
        lenid_modulo = lenid_sum % 16
        lenid_invert_plus_one = 0b1111 - lenid_modulo + 1

        return (lenid_invert_plus_one << 12) + lenid


    def send_cmd(self, ver: int, address: int, cmd, info: bytes = b''):
        raw_frame = self._encode_cmd(ver, address, cmd, info)
        self.s.write(raw_frame)


    def _encode_cmd(self, ver: int, address: int, cid2: int, info: bytes = b''):
        cid1 = 0x46

        info_length = Pylontech.get_info_length(info)

        frame = "{:02X}{:02X}{:02X}{:02X}{:04X}".format(ver, address, cid1, cid2, info_length).encode()
        frame += info

        frame_chksum = Pylontech.get_frame_checksum(frame)
        whole_frame = (b"~" + frame + "{:04X}".format(frame_chksum).encode() + b"\r")
        return whole_frame


    def _decode_hw_frame(self, raw_frame: bytes) -> bytes:
        # XXX construct
        frame_data = raw_frame[1:len(raw_frame) - 5]
        frame_chksum = raw_frame[len(raw_frame) - 5:-1]

        got_frame_checksum = Pylontech.get_frame_checksum(frame_data)
        assert got_frame_checksum == int(frame_chksum, 16)

        return frame_data

    def _decode_frame(self, frame):
        format = construct.Struct(
            "ver" / HexToByte(construct.Array(2, construct.Byte)),
            "adr" / HexToByte(construct.Array(2, construct.Byte)),
            "cid1" / HexToByte(construct.Array(2, construct.Byte)),
            "cid2" / HexToByte(construct.Array(2, construct.Byte)),
            "infolength" / HexToByte(construct.Array(4, construct.Byte)),
            "info" / HexToByte(construct.GreedyRange(construct.Byte)),
        )

        return format.parse(frame)


    def read_frame(self):
        raw_frame = self.s.readline()
        f = self._decode_hw_frame(raw_frame=raw_frame)
        parsed = self._decode_frame(f)
        return parsed

    def get_analog_values(self, addr):
        info = "{:02X}".format(addr).encode()
        self.send_cmd(0x25, addr, 0x42, info)
        f = self.read_frame()

        # infoflag = f.info[0]
        d = self.pace_analog_fmt.parse(f.info[1:])

        data = {
            "address": d.Address,
            "number_of_cells": d.NumberOfCells,
            "cell_voltages": d.CellVoltages[:],
            "number_of_temperatures": d.NumberOfTemperatures,
            "temperatures": d.Temperatures[:],
            "current": d.Current,
            "voltage": d.Voltage,
            "remaining_capacity": d.RemainingCapacity,
            "total_capacity": d.TotalCapacity,
            "cycle_number": d.CycleNumber,
            "design_capacity": d.DesignCapacity

        }
        return data

if __name__ == '__main__':
    p = Pylontech()
    print(json.dumps(p.get_analog_values(0)))


