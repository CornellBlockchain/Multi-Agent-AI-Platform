# Computer Networks: Transport Layer

## TCP Congestion Control
TCP congestion control adjusts how much unacknowledged data a sender can keep in the network. When packet loss suggests congestion, a TCP sender typically reduces its sending rate or congestion window. The precise response depends on the congestion-control algorithm. Acknowledgments help the sender learn when data has arrived and when it may increase its sending rate.

## Reliable Delivery and Retransmission
TCP uses sequence numbers and acknowledgments to provide ordered, reliable byte-stream delivery. When segments are lost, retransmissions can recover missing data. Timeouts and duplicate acknowledgments may help indicate that retransmission is necessary.

## Three-Way Handshake
A TCP connection normally begins with SYN, SYN-ACK, and ACK messages. This handshake establishes initial sequence-number state before application data is exchanged.
