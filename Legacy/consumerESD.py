#!/usr/bin/env python3
# -*- coding: utf-8 -*-

'''
Example for RCAing like a B0$$
'''
import requests
import json

# from kafka import KafkaConsumer

import pickle
import time
import numpy as np
import pandas as pd
from scipy.stats import t
from termcolor import colored
from sklearn import preprocessing
from sklearn.cluster import Birch
from sklearn.neighbors import KernelDensity
from threading import Thread, Lock


class ESB_Analyzer():
    def __init__(self, esb_data):
        self.esb_data = esb_data
        self.initialize()

    def initialize(self):
        filename = 'birch_model_avgtime.sav'
        self.avg_time_model = pickle.load(open(filename, 'rb'))
        filename = 'birch_model_success.sav'
        self.succee_rate_model = pickle.load(open(filename, 'rb'))
        print('ESB models loaded')

    def update_esb_data(self, esb_data):
        self.esb_data = esb_data

    def birch(self, values, ctype):  # values should be a list
        X = np.reshape(values, (-1, 1))
        brc = self.avg_time_model if ctype == "time" else self.succee_rate_model
        return brc.predict(X)

    def analyze_esb(self, esb_dict):
        esb_tmp = self.esb_data.append(esb_dict, ignore_index=True)
        values = esb_tmp['avg_time'].tolist()
        # print(values)
        birch_labels_time = self.birch(values,"time")
        # birch_labels_rate = self.birch(self.esb_data['avg_time'])
        for label in birch_labels_time:
            if (label != 0):
                print("Found esb_anomaly in avg_time")
                return True

        values = esb_tmp['succee_rate'].tolist()
        # print(values)
        birch_labels_time = self.birch(values,"rate")
        for label in birch_labels_time:
            if (label != 0):
                print("Found esb_anomaly in success rate")
                return True

        self.update_esb_data(esb_tmp)

        return False


class RCA():
    def __init__(self, trace_data, host_data, alpha=0.95, ub=0.02, take_minute_averages_of_trace_data=True, division_milliseconds=60000):
        self.trace_data = trace_data
        self.host_data = host_data
        self.alpha = alpha
        self.ub = ub
        self.anomaly_chart = None
        self.take_minute_averages_of_trace_data = take_minute_averages_of_trace_data
        self.division_milliseconds = division_milliseconds

    def run(self):
        self.trace_processing()
        
        print('Running RCA on %d trace data rows and %d host data rows' %
              (len(self.trace_data), len(self.host_data)))
        overall_start_time = time.time()

        print('Computing for anomaly score chart...')
        self.hesd_trace_detection(alpha=self.alpha, ub=self.ub)
        print('Score chart computed!')

        self.local_initiate()
        output = self.find_anomalous_rows()

        print('The output to send to the server is: ' +
              colored(str(output), 'magenta'))

        print('RCA finished in ' + colored('%f', 'cyan') %
              (time.time() - overall_start_time) + ' seconds.')

        return output

    def esd_test_statistics(self, x, hybrid=True):
        """
        Compute the location and dispersion sample statistics used to carry out the ESD test.
        """
        if hybrid:
            location = pd.Series(x).median(skipna=True) # Median
            dispersion = np.median(np.abs(x - np.median(x))) # Median Absolute Deviation
        else:  
            location = pd.Series(x).mean(skipna=True) # Mean
            dispersion = pd.Series(x).std(skipna=True) # Standard Deviation
            
        return location, dispersion

    def esd_test(self, x, alpha=0.95, ub=0.499, hybrid=True):
        """
        Carries out the Extreme Studentized Deviate(ESD) test which can be used to detect one or more outliers present in the timeseries
        
        x      : List, array, or series containing the time series
        freq   : Int that gives the number of periods per cycle (7 for week, 12 for monthly, etc)
        alpha  : Confidence level in detecting outliers
        ub     : Upper bound on the fraction of datapoints which can be labeled as outliers (<=0.499)
        hybrid : Whether to use the robust statistics (median, median absolute error) or the non-robust versions (mean, standard deviation) to test for anomalies
        """
        nobs = len(x)
        if ub > 0.4999:
            ub = 0.499
        k = max(int(np.floor(ub * nobs)), 1) # Maximum number of anomalies. At least 1 anomaly must be tested.
        #   res_tmp = ts_S_Md_decomposition(x)["residual"] # Residuals from time series decomposition
        # res_tmp = np.abs(x - np.median(x))
        # Carry out the esd test k times  
        res = np.ma.array(x, mask=False) # The "ma" structure allows masking of values to exclude the elements from any calculation
        anomalies = [] # returns the indices of the found anomalies
        med = np.median(x)
        for i in range(1, k+1):
            location, dispersion = self.esd_test_statistics(res, hybrid) # Sample statistics
            tmp = np.abs(res - location) / dispersion
            idx = np.argmax(tmp) # Index of the test statistic
            test_statistic = tmp[idx]
            n = nobs - res.mask.sum() # sums  nonmasked values
            critical_value = (n - i) * t.ppf(alpha, n - i - 1) / np.sqrt((n - i - 1 + np.power(t.ppf(alpha, n - i - 1), 2)) * (n - i - 1)) 
            if test_statistic > critical_value:
                anomalies.append((x[idx]-med) / med)
                # anomalies.append(test_statistic)
            res.mask[idx] = True
        if len(anomalies) == 0:
            return 0
        return np.mean(np.abs(anomalies))
    
    def hesd_trace_detection(self, alpha=0.95, ub=0.02):
        grouped_df = self.trace_data.groupby(['cmdb_id', 'serviceName'])[['startTime','actual_time']]

        self.anomaly_chart = pd.DataFrame()
        for (a, b), value in grouped_df:
            value['time_group'] = value.startTime//self.division_milliseconds
            value = value.groupby(['time_group'])['actual_time'].mean().reset_index()
            result = self.esd_test(value['actual_time'].to_numpy(), alpha=alpha, ub=ub, hybrid=True)
            self.anomaly_chart.loc[b,a] = result

        self.anomaly_chart = self.anomaly_chart.sort_index()
        print(self.anomaly_chart)
        # print(self.anomaly_chart.to_dict())
        return self.anomaly_chart
    
    def local_initiate(self):
        self.dockers = ['docker_001', 'docker_002', 'docker_003', 'docker_004',
                'docker_005', 'docker_006', 'docker_007', 'docker_008']
        self.docker_hosts = ['os_017', 'os_018', 'os_019', 'os_020']

        self.docker_kpi_names = ['container_cpu_used', None]
        self.os_kpi_names = ['Sent_queue', 'Received_queue']
        self.db_kpi_names = ['Proc_User_Used_Pct','Proc_Used_Pct','Sess_Connect','On_Off_State', 'tnsping_result_time']

        self.docker_lookup_table = {}
        for i in range(len(self.dockers)):
            self.docker_lookup_table[self.dockers[i]] = self.docker_hosts[i % 4]


    def find_anomalous_rows(self, min_threshold = 5):
        table = self.anomaly_chart.copy()
        threshold = max( 0.5 * table.stack().max(), min_threshold)
        dodgy_rows = []
        just_rows = []
        row_col_dict = {}
        for column in table:
            v = 0
            r = ''
            for index, row in table.iterrows():
                if (row[column] > threshold):
                    if index == column:
                        dodgy_rows.append([index, column, row[column]])
                        just_rows.append(index)
                        row_col_dict[index] = True
                        break
                    elif (row[column] > v):
                        v = row[column]
                        r = index
            if r != '':
                dodgy_rows.append([r, column, v])
                just_rows.append(r)
                if r not in row_col_dict.keys():
                    row_col_dict[r] = False
        
        output = self.localize(dodgy_rows, list(set(just_rows)), row_col_dict)
        return output


    def find_anomalous_kpi(self, cmdb_id, row_col_same = False):
        kpi_names = []
        if 'os' in cmdb_id:
            kpi_names = self.os_kpi_names
        elif 'docker' in cmdb_id:
            kpi_names = [self.docker_kpi_names[0]] if row_col_same else [self.docker_kpi_names[1]]
        else:
            kpi_names = self.db_kpi_names
            host_data_subset = self.host_data.loc[(self.host_data.cmdb_id == cmdb_id) & (self.host_data.name.isin(kpi_names))]
            results_dict = {}
            for kpi, values in host_data_subset.groupby('name')['value']:
                values = list(values)
                score =  self.esd_test(np.array(values), 0.95, 0.1, True)
                results_dict[kpi] = score
            db_connection_limit = [results_dict['Proc_User_Used_Pct'],results_dict['Proc_Used_Pct'],results_dict['Sess_Connect']]
            db_connection_limit_score = np.mean(db_connection_limit)
            db_close = [results_dict['On_Off_State'],results_dict['tnsping_result_time']]
            db_close_score = np.mean(db_close)
            if db_connection_limit_score > db_close_score:
                kpi_names = kpi_names[:3]
            else:
                kpi_names = kpi_names[3:]             

        return kpi_names


    def localize(self, dodgy_rows, just_rows, row_col_dict):
        n = len(just_rows)
        print('%d anomalies found' % n)
        if n < 1:
            return None
        if n == 1:
            KPIs = self.find_anomalous_kpi(just_rows[0], row_col_dict[list(row_col_dict.keys())[0]])
            to_be_sent = []
            for KPI in KPIs:
                to_be_sent.append([just_rows[0], KPI])
            return to_be_sent
        if n == 2:
            r0 = just_rows[0]
            r1 = just_rows[1]
            if ('os' in r0) and ('os' in r1):
                KPIS = self.find_anomalous_kpi('os_001')
                return [['os_001', KPIS[0]], ['os_001', KPIS[1]]]

            if ('docker' in r0) and ('docker' in r1):
                if self.docker_lookup_table[r0] == self.docker_lookup_table[r1]:
                    KPIS = self.find_anomalous_kpi(self.docker_lookup_table[r0])
                    to_be_sent = []
                    for kpi in KPIS:
                        to_be_sent.append([self.docker_lookup_table[r0], kpi])
                    return to_be_sent

            KPI0s = self.find_anomalous_kpi(r0, row_col_dict[r0])
            KPI1s = self.find_anomalous_kpi(r1, row_col_dict[r1])
            to_be_sent = []
            for kpi in KPI0s:
                to_be_sent.append([r0, kpi])
            for kpi in KPI1s:
                to_be_sent.append([r1, kpi])
            return to_be_sent
        if n > 2:
            dodgy_rows.sort(key = lambda x: x[2], reverse = True)
            just_rows = [x[0] for x in dodgy_rows]
            just_rows = list(np.unique(just_rows))
            row_col_dict = { just_rows[0]: row_col_dict[just_rows[0]], just_rows[1]: row_col_dict[just_rows[1]] } 
            return self.localize(dodgy_rows[:2], just_rows[:2], row_col_dict)


    def update_trace_data(self, trace_data):
        self.trace_data = trace_data

    def update_host_data(self, host_data):
        self.host_data = host_data

    def trace_processing(self):
        print("Started trace processing")
        p_time = time.time()
        self.trace_data = self.trace_data[self.trace_data['callType'] != 'FlyRemote'].copy()
        df1 = self.trace_data[self.trace_data['callType']=='RemoteProcess']
        df1 = df1[['pid','cmdb_id']]
        df1 = df1.set_index('pid')

        # csf_cmdb = df1.to_dict()
        # csf_cmdb = {str(key):str(values) for key, values in csf_cmdb['cmdb_id'].items()}

        # for index, row in self.trace_data.iterrows():
        #     if row['id'] in csf_cmdb:
        #         self.trace_data.at[index, 'serviceName'] = csf_cmdb[row['id']]

        elapse_time = {}
        children = {}

        def do_thing(row):
            ## if change 297 and 298, gets different result??? loook into this plz
            if row['id'] in df1.index:
                row['serviceName'] = df1.at[row['id'],'cmdb_id']
            if row['pid'] != 'None':
                children[row['pid']] = children.get(row['pid'], [])
                children[row['pid']].append(row['id'])
            elapse_time[row['id']] = float(row['elapsedTime'])
            return row
        self.trace_data = self.trace_data.apply(do_thing, axis=1)


        # for index, row in self.trace_data.iterrows():
        #     if row['pid'] != 'None':
        #         if row['pid'] in children.keys():
        #             children[row['pid']].append(row['id'])
        #         else:
        #             children[row['pid']] = [row['id']]
        #     elapse_time[row['id']] = float(row['elapsedTime'])
        
        # self.trace_data.apply(parse, axis = 1)

        self.trace_data['actual_time'] = 0.0
        # for index, row in self.trace_data.iterrows():
        #     total_child = 0.0
        #     if row['id'] not in children.keys():
        #         self.trace_data.at[index, 'actual_time'] = row['elapsedTime']
        #         continue
        #     for child in children[row['id']]:
        #         total_child += elapse_time[child]
        #     self.trace_data.at[index, 'actual_time'] = row['elapsedTime'] - total_child

        def get_actual_time(row):
            total_child = 0.0
            if row['id'] in children:
                for child in children[row['id']]:
                    total_child += elapse_time[child]
            row['actual_time'] = row['elapsedTime'] - total_child
            return row
        
        self.trace_data = self.trace_data.apply(get_actual_time, axis = 1)
        
        self.trace_data = self.trace_data[~(self.trace_data['serviceName'].str.contains('csf', na=True))]

        print("Trace processed in ", time.time()-p_time, 'seconds')
        print(self.trace_data)


# Three topics are available: platform-index, business-index, trace.
# Subscribe at least one of them.
AVAILABLE_TOPICS = set(['platform-index', 'business-index', 'trace'])
# CONSUMER = KafkaConsumer('platform-index', 'business-index', 'trace',
#                          bootstrap_servers=['172.21.0.8', ],
#                          auto_offset_reset='latest',
#                          enable_auto_commit=False,
#                          security_protocol='PLAINTEXT')


class Trace():  # pylint: disable=invalid-name,too-many-instance-attributes,too-few-public-methods
    '''Structure for traces'''

    __slots__ = ['call_type', 'start_time', 'elapsed_time', 'success',
                 'trace_id', 'id', 'pid', 'cmdb_id', 'service_name', 'ds_name']

    def __new__(self, data):
        self.trace = data
        if self.trace['callType'] == 'JDBC' or self.trace['callType']=='LOCAL':
            try:
                self.trace['serviceName'] = data['dsName']
            except:
                print(data)
                print('JDBC doesnt have dsName')
        
        elif self.trace['callType']=='RemoteProcess' or self.trace['callType']=='OSB':
            self.trace['serviceName'] = data['cmdb_id']

        if 'dsName' in self.trace:
            self.trace.pop('dsName')

        return self.trace


def detection(timestamp):
    global host_df, trace_df
    print('Starting Anomaly Detection')
    startTime = timestamp - 300000  # one minute before anomaly

    # print(len(trace_df), trace_df.head())
    # print(len(host_df), host_df.head())
    trace_df_temp = trace_df[(trace_df['startTime'] >= startTime) &
                             (trace_df['startTime'] <= timestamp)]
    host_df_temp = host_df[(host_df['timestamp'] >= startTime) &
                           (host_df['timestamp'] <= timestamp)]
    print(len(trace_df_temp), trace_df_temp.head())
    print(len(host_df_temp), host_df_temp.head())

    rca_temp = RCA(trace_data=trace_df_temp, host_data=host_df_temp)
    results_to_send_off = rca_temp.run()

    print('Anomaly Detection Done.')
    if results_to_send_off is None:
        # print('Nothing detected')
        return False
    # for a in anom_hosts:
    #     item = a.split(':')[0]
    #     if (item not in anoms):
    #         anoms.append(item)
    print(results_to_send_off)
    # submit(results_to_send_off)
    return True


def rcaprocess(esb_item, trace, host, timestamp, lock):
    global host_df, trace_df, esb_anal, a_time
    esb_anomaly = False

    # print(trace)
    trace_df = trace_df[(trace_df.startTime >= (timestamp-1200000))]
    host_df = host_df[(host_df.timestamp >= (timestamp-1200000))]
    
    t = time.time()
    t_df = pd.DataFrame(trace)
    h_df = pd.DataFrame(host)

    trace_df = pd.concat([trace_df, t_df], axis=0, ignore_index=True)
    host_df = pd.concat([host_df, h_df], axis=0, ignore_index=True)

    print('Time to add new data: ', (time.time()-t))

    print(esb_anal.esb_data.tail(1))
    print(host_df.tail(1))
    print(trace_df.tail(1))

    with lock:
        esb_anomaly = esb_anal.analyze_esb(esb_item)
        if (time.time() - a_time) >= 600 and esb_anomaly:
            tmp_time = time.time()
            print("oops")
            # detection(timestamp)
            result = detection(timestamp)
            print('Anomaly at: ', timestamp)
            if result:
                a_time = tmp_time


def submit(ctx):
    '''Submit answer into stdout'''
    # print(json.dumps(data))
    assert (isinstance(ctx, list))
    for tp in ctx:
        assert(isinstance(tp, list))
        assert(len(tp) == 2)
        assert(isinstance(tp[0], str))
        assert(isinstance(tp[1], str) or (tp[1] is None))
    data = {'content': json.dumps(ctx)}
    r = requests.post('http://172.21.0.8:8000/standings/submit/', data=json.dumps(data))


# esb_df = pd.DataFrame(columns=[
#                       'serviceName', 'startTime', 'avg_time', 'num', 'succee_num', 'succee_rate'])
# host_df = pd.DataFrame(
#     columns=['itemid', 'name', 'bomc_id', 'timestamp', 'value', 'cmdb_id'])
# trace_df = pd.DataFrame(columns=['callType', 'startTime', 'elapsedTime',
#                                  'success', 'traceId', 'id', 'pid', 'cmdb_id', 'serviceName'])
# esb_anal = ESB_Analyzer(esb_df)
# a_time = 0.0


def main():
    '''Consume data and react'''
    assert AVAILABLE_TOPICS <= CONSUMER.topics(), 'Please contact admin'

    global esb_df, host_df, trace_df, esb_anal, a_time

    esb_df = pd.DataFrame(columns=[
                          'serviceName', 'startTime', 'avg_time', 'num', 'succee_num', 'succee_rate'])
    host_df = pd.DataFrame(
        columns=['itemid', 'name', 'bomc_id', 'timestamp', 'value', 'cmdb_id'])
    trace_df = pd.DataFrame(columns=['callType', 'startTime', 'elapsedTime',
                                     'success', 'traceId', 'id', 'pid', 'cmdb_id', 'serviceName'])
    esb_anal = ESB_Analyzer(esb_df)
    a_time = 0.0

    lock = Lock()

    print('Started receiving data! Fingers crossed...')

    # Dataframes for the three different datasets

    trace_list = []
    host_list = []

    for message in CONSUMER:
        data = json.loads(message.value.decode('utf8'))

        # Host data
        if message.topic == 'platform-index':
            for stack in data['body']:
                for item in data['body'][stack]:
                    # host_df = host_df.append(item, ignore_index=True)
                    host_list.append(item)

        # ESB data
        elif message.topic == 'business-index':
            timestamp = data['startTime']

            esb_item = data['body']['esb'][0]

            try:
                Thread(target=rcaprocess, args=(esb_item, trace_list, host_list, timestamp, lock)).start()
            except:
                print("Error: unable to start rcaprocess")

            trace_list = []
            host_list = []

        # Trace data
        else:  # message.topic == 'trace'
            # print(data)
            trace_list.append(Trace(data))

if __name__ == '__main__':
    # main()

    '''
        Bellow are for testing purposes
    # # '''
    
    # global host_df, trace_df

    # path = r'D:\\THU Studies\Advance Network Management\\Project\Anomaly-detection\\local_data\\'
    # trace_df = pd.read_csv(path + 'esd\\trace526209_db007.csv')
    # trace_df = trace_df.drop(['actual_time'], axis=1)
    # trace_df = trace_df.sort_values(by=['startTime'], ignore_index=True)
    # # trace = trace[trace.startTime < trace.startTime[0]+1260000]

    # host_df = pd.read_csv(path + 'kpi_data_526_db_007.csv')
    # host_df = host_df.sort_values(by=['timestamp'], ignore_index=True)

    # # print(trace_df)
    # print(host_df)
    # timestamp = int(host_df['timestamp'].iloc[-1]-180000)
    # print()
    # print(timestamp)
    # trace_df = trace_df[(trace_df.startTime >= (timestamp-1260000))]
    # print(host_df)
    # detection(timestamp)
 