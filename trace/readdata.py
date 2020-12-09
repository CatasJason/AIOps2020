import numpy as np
import random
import json


def read_raw_vector(input_json, vc=None, shuffle=True, sample=None):  # flows, vectors, valid_column
    # with open(input_file, 'r') as fin:
    #     raw = fin.read().strip().split('\n')

    data = json.load(open(input_json))

    flows = list()
    vectors = list()

    for key, value in data.items():
        flows.append(key)
        vectors.append(value)
        
    if shuffle is True:
        arr_index = np.arange(len(vectors))
        np.random.shuffle(arr_index)
        shuffled_vectors = []
        for index in arr_index:
            shuffled_vectors.append(vectors[index])
        vectors = shuffled_vectors

    if sample is not None:
        vectors = random.sample(vectors, sample)
    vectors = np.array(vectors)

    n = len(vectors)
    m = len(vectors[0])

    if vc is None:
        valid_column = list()

        for i in range(0, m):
            flag = False
            for j in range(0, n):
                if vectors[j, i] > 0:
                    flag = True
                    break
            if flag:
                valid_column.append(i)
    else:
        valid_column = vc

    vectors = vectors[:, valid_column]
    return flows, vectors, valid_column


def get_mean_std(matrix):
    mean = []
    std = []
    for item in np.transpose(matrix):
        mean.append(np.mean(item[item>0.00001]))
        std.append(max(1, np.std(item[item>0.00001])))
    
    return mean, std


def normalization(matrix, mean, std):
    n_mat = np.array(matrix, dtype=np.float32)
    n_mat = np.where(n_mat<0.00001, -1, (n_mat - mean) / std)
    return n_mat

def get_train_data(train_file, sample=None):
    _, train_raw, valid_columns = read_raw_vector(train_file, sample=sample)
    train_mean, train_std = get_mean_std(train_raw)
    train_x = normalization(train_raw, train_mean, train_std)
    train_y = np.zeros(len(train_x), dtype=np.int32)
    return (train_x, train_y)


def get_data_vae(train_file, normal_file, abnormal_file):
    _, train_raw, valid_columns = read_raw_vector(train_file)
    flows1, normal_raw, _ = read_raw_vector(normal_file, valid_columns, shuffle=False)
    flows2, abnormal_raw, _ = read_raw_vector(abnormal_file, valid_columns, shuffle=False)

    train_mean, train_std = get_mean_std(train_raw)
    train_x = normalization(train_raw, train_mean, train_std)
    normal_x = normalization(normal_raw, train_mean, train_std)
    abnormal_x = normalization(abnormal_raw, train_mean, train_std)
    
    print('abnormal')
    for i in range(30):
        print(list(abnormal_x[i]))

    train_y = np.zeros(len(train_x), dtype=np.int32)
    normal_y = np.zeros(len(normal_x), dtype=np.int32)
    abnormal_y = np.ones(len(abnormal_x), dtype=np.int32)

    test_x = np.concatenate([normal_x, abnormal_x])
    test_y = np.concatenate([normal_y, abnormal_y])
    test_flow = flows1 + flows2

    return (train_x, train_y), (test_x, test_y), test_flow


def get_z_dim(x_dim):
    tmp = x_dim
    z_dim = 5
    while tmp > 20:
        z_dim *= 2
        tmp = tmp // 20
    return z_dim
