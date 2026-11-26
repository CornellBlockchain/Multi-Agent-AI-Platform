# Database Systems: Storage and Transactions

## ACID Transactions
Database transactions are often described by ACID properties. Atomicity means a transaction's changes are treated as a unit: they either commit together or are rolled back. Consistency concerns preserving defined database rules. Isolation describes how concurrent transactions interact. Durability means committed changes survive failures according to the database's recovery guarantees.

## Indexes and B-Trees
A database index helps locate matching rows without scanning an entire table. B-tree-family indexes organize keys in an ordered structure, which makes range queries and exact lookups efficient for many workloads. Indexes also create storage and update overhead.

## Concurrent Transactions
Concurrency control prevents unwanted interactions between overlapping operations. Common mechanisms include locks, multi-version concurrency control, and transaction isolation levels. Stronger isolation can reduce anomalies but may introduce additional coordination costs.
