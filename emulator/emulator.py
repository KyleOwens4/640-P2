import argparse
import logging
import random
import socket
import struct
import time
from datetime import datetime


class ForwardingEntry:
    def __init__(self, row_columns):
        self.emulator_host_name = row_columns[0]
        self.emulator_port = int(row_columns[1])
        self.destination_host_name = row_columns[2]
        self.destination_port = int(row_columns[3])
        self.next_hop_host_name = row_columns[4]
        self.next_hop_port = int(row_columns[5])
        self.delay = int(row_columns[6])
        self.loss_probability = row_columns[7]


class ForwardingQueue:
    def __init__(self, max_size):
        self.priority_queue1 = []
        self.priority_queue2 = []
        self.priority_queue3 = []
        self.max_size = max_size
        self.delayed_packet = None
        self.delay_start = None

    def queue_packet(self, packet, delay, drop_prob):
        if packet.priority == 1:
            if len(self.priority_queue1) < self.max_size:
                self.priority_queue1.append([packet, delay, drop_prob])
            else:
                log_event('Priority queue 1 was full', packet)
        elif packet.priority == 2:
            if len(self.priority_queue2) < self.max_size:
                self.priority_queue2.append([packet, delay, drop_prob])
            else:
                log_event('Priority queue 2 was full', packet)
        elif packet.priority == 3:
            if len(self.priority_queue3) < self.max_size:
                self.priority_queue3.append([packet, delay, drop_prob])
            else:
                log_event('Priority queue 3 was full', packet)

    def get_next_packet(self):
        if len(self.priority_queue1) > 0:
            return self.priority_queue1.pop(0)
        elif len(self.priority_queue2) > 0:
            return self.priority_queue2.pop(0)
        elif len(self.priority_queue3) > 0:
            return self.priority_queue3.pop(0)
        else:
            return None

    def update_queue(self):
        if self.delayed_packet is None:
            self.delayed_packet = self.get_next_packet()
            self.delay_start = int(time.time() * 1000)

        if self.delayed_packet is not None:
            if int(time.time() * 1000) - self.delay_start >= self.delayed_packet[1]:
                packet = self.delayed_packet[0]
                packet.drop_prob = self.delayed_packet[2]

                self.delayed_packet = None
                self.delay_start = None

                return packet

        return None


class Packet:
    def __init__(self, packet, from_address):
        outer_header = packet[:17]
        inner_header = packet[17:26]

        self.priority, self.int_src_ip, self.src_port, self.int_dest_ip, self.dest_port, self.outer_length = struct.unpack("!BIHIHI", outer_header)
        self.src_ip = self.convert_int_to_ip(self.int_src_ip)
        self.src_hostname = socket.gethostbyaddr(self.src_ip)[0]
        self.dest_ip = self.convert_int_to_ip(self.int_dest_ip)
        self.dest_hostname = socket.gethostbyaddr(self.dest_ip)[0]

        self.type, self.seq_num, self.length = struct.unpack("!cII", inner_header)
        self.type = str(self.type, 'UTF-8')
        self.seq_num = socket.ntohl(self.seq_num)

        self.data = packet[26:]
        self.data = self.data.decode() if len(self.data) > 0 else ''

        self.packet = packet
        self.from_address = from_address
        self.next_hop_address = None
        self.drop_prob = 0

        if args.d:
            self.print_debug_info()

    def convert_int_to_ip(self, int_ip):
        return socket.inet_ntoa(struct.pack('!L', int_ip))

    def print_debug_info(self):
        print('==============INCOMING PACKET===============')
        print('Priority         ' + str(self.priority))
        print('Source Name      ' + str(self.src_hostname))
        print('Source IP        ' + str(self.src_ip))
        print('Source Port      ' + str(self.src_port))
        print('Destination Name ' + str(self.dest_hostname))
        print('Destination IP   ' + str(self.dest_ip))
        print('Destination Port ' + str(self.dest_port))
        print('Outer Packet Len ' + str(self.outer_length))
        print('Type             ' + str(self.type))
        print('Sequence Number  ' + str(self.seq_num))
        print('Inner Packet Len ' + str(self.length))
        print('Data:            ' + str(self.data[:4]))
        print('From Addr        ' + str(self.from_address[0]))
        print('From Port        ' + str(self.from_address[1]))
        print('============================================')
        print('')



class EmulatorSocket:
    def __init__(self, listening_port_num):
        self.listen_address = (socket.gethostbyname(socket.gethostname()), listening_port_num)
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket.bind(self.listen_address)
        self.socket.settimeout(0)

    def send_packet(self, packet):
        self.socket.sendto(packet.packet, packet.next_hop_address)

    def await_packet(self):
        full_packet, from_address = self.socket.recvfrom(5500)

        return Packet(full_packet, from_address)


def get_args():
    parser = argparse.ArgumentParser(usage="emulator.py -p <port> -q <queue_size> -f <filename> -l <log>")

    parser.add_argument('-p', choices=range(2050, 65536), type=int,
                        help='Port number emulator should wait for packets on', required=True)
    parser.add_argument('-q', type=int, help='Size of each queue', required=True)
    parser.add_argument('-f', type=str, help='Name of the file containing the static forwarding table', required=True)
    parser.add_argument('-l', type=str, help='Name of the log file', required=True)
    parser.add_argument('-d', type=bool, default=False, help='Debug mode', required=False)

    return parser.parse_args()


def log_event(message, packet):
    logging.warning('reason: ' + message +
                    ' source host: ' + packet.src_hostname +
                    ' source port: ' + str(packet.src_port) +
                    ' dest host: ' + packet.dest_hostname +
                    ' dest port: ' + str(packet.dest_port) +
                    ' time of loss: ' + str(datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]) +
                    ' priority level: ' + str(packet.priority) +
                    ' payload size: ' + str(packet.outer_length))


def load_forwarding_table(filename, port):
    forwarding_entries = []

    try:
        file = open(filename, 'r')
    except IOError as e:
        print(str(e))
        exit(-1)

    lines = file.readlines()
    for line in lines:
        cols = line.split(' ')

        if cols[0] == socket.gethostname() and int(cols[1]) == port:
            forwarding_entries.append(ForwardingEntry(cols))

    return forwarding_entries


def get_forwarding_entry(packet, forwarding_table):
    for forwarding_entry in forwarding_table:
        if forwarding_entry.destination_host_name == packet.dest_hostname and forwarding_entry.destination_port == packet.dest_port:
            packet.next_hop_address = (socket.gethostbyname(forwarding_entry.next_hop_host_name), forwarding_entry.next_hop_port)
            return forwarding_entry

    return None


def should_send(outgoing_packet):
    if outgoing_packet is None:
        return False

    if outgoing_packet.type == 'E':
        return True

    if random.randint(1, 100) <= int(outgoing_packet.drop_prob):
        log_event('Loss event occurred', outgoing_packet)
        return False

    return True


def listen_for_packets(forwarding_table, emulator_socket, args):
    forwarding_queue = ForwardingQueue(args.q)

    while True:
        try:
            incoming_packet = emulator_socket.await_packet()

            forwarding_entry = get_forwarding_entry(incoming_packet, forwarding_table)
            if forwarding_entry is not None:
                forwarding_queue.queue_packet(incoming_packet, forwarding_entry.delay, forwarding_entry.loss_probability)
            else:
                log_event('No forwarding entry found', incoming_packet)

        except BlockingIOError as e:
            pass

        outgoing_packet = forwarding_queue.update_queue()
        if should_send(outgoing_packet):
            emulator_socket.send_packet(outgoing_packet)


if __name__ == '__main__':
    args = get_args()

    logging.basicConfig(filename=args.l, encoding='utf-8', filemode='w')
    forwarding_table = load_forwarding_table(args.f, args.p)

    listen_for_packets(forwarding_table, EmulatorSocket(args.p), args)