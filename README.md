# Anomaly detection

> This is the group project for ANM2020.

## Guide

### Running Scripts in Tencent Cloud
- Make sure python scipt has the following at the beginning
   ```
   #!/usr/bin/env python3
   ```
- Give it permission
   ```
   chmod +x main.py
   ```
- Run it using:
   ```
   nohup python -u ./consumer.py > [output file name].log &
   ```

### Viewing the output
   ```
   cat [output file name].log
   ```

### To end the process
   ```
   ps ax | grep consumer.py
   kill PID
   ```

### Scripts
- consumer.py --- script to submit our answers
- concat.py --- script to make a single file for all data

### Main program
- main.py --- main python file that we can use for our submission
- main.ipynb --- notebook to finish different parts of the task efficiently

## Problem statement

> Root cause an anomaly for a microservice-based software system.

### Definitions

1. **Anomaly detection**: Considering the time series behavior of the system, label values that exceed an arbitrary threshold as anomalies.

2. **Troubleshooting**: refers to the task of finding the root cause of failure and fixing it. It has 3 steps:

   1. Find time t when success rate is much lower than 1
   2. Around that time, check the behavior of microservices and other hosts and containers.
   3. After finding the abnormal source, find which KPIs perform anomalously.

3. **Microservice system**

   1. The user send a request (UUID-n).
   2. The Remote Procedure Call (RPC) Framework makes consecutive calls to different micro-services to process user's request.
   3. The web service posts a response (UUID-n)

   | MSG Order |  UUID  |  Sent at   | Received at |  MSG (m->n)   |
   | :-------: | :----: | :--------: | :---------: | :-----------: |
   |     1     | UUID-1 | 1516171819 | 1516171821  | call(start a) |
   |     2     | UUID-1 | 1516171820 | 1516171821  |  call(a - b)  |
   |     3     | UUID-1 | 1516171821 | 1516171822  | response(b-a) |

### Data sources

1. **ESB business indicator (ESB)**

   | Service name | Start time | Average time | num: # requests | # success | Success rate |
   | :----------: | :--------: | :----------: | :-------------: | :-------: | :----------: |
   |   osb_001    | 1516171819 |   0.45678    |       360       |    360    |     1.0      |
   |   osb_001    | 1516171819 |   0.45678    |       461       |    461    |     1.0      |

   We only have osb_001 so we can *neglect* this column. The data is recorded every **minute**.

   

2. **Trace**: a user request (with a unique ID) --- it consists of several microservice calls (AKA *span*). Each *span* has a tree structure; therefore, each span has a parent span, except for the root span. There are also two types of *span*: **inside and outside**.

   |  ID  | Parent ID | Trace ID | Start time | Elapsed time | Service name | cmdb ID | Call type | Success | ds name |
   | :--: | :-------: | :------: | :--------: | :----------: | :----------: | :-----: | :-------: | :-----: | :-----: |
   |  1   |   None    |    1     |     t1     |    t2-t1     |     foo      | db_008  |    osb    |  True   |    -    |
   |  2   |     1     |    2     |     t3     |    t4-t3     |     bar      | db_008  |    csf    |  True   |    -    |
   |  3   |     2     |    3     |     t5     |    t6-t5     |     bar      | db_009  |   local   |  False  |   ANM   |

   **callType**: has 6 types.

   inside spans: 1. osb 2. remoteprocess 3. flyremote

   outside spans: 4. csf 5. local 6. jdbc

   **dsName**: named of the database accessed by the microservice, only when local of jdbc (where we can regard accessing databases as the microservice).

   

3. **Host KPIs data**

   | Item ID |   Name   | Bomc ID |  Timestamp   | Value  | cmdb ID |
   | :-----: | :------: | :-----: | :----------: | :----: | :-----: |
   |  1111   | CPU_free |  ZJ02   | 163249574938 | 420.69 | db_008  |

