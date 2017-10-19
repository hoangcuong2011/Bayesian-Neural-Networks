#!/usr/bin/env python
# -*- coding: utf-8 -*-

from __future__ import absolute_import
from __future__ import print_function
from __future__ import division
import os

import copy



import tensorflow as tf
from six.moves import range, zip
import numpy as np
import zhusuan as zs

from examples import conf
from examples.utils import dataset


def standardize_data(X_train, X_test, X_valid):
    X_mean = np.mean(X_train, axis=0)
    X_std = np.std(X_train, axis=0)

    X_train -= X_mean
    X_train /= X_std
    X_test -= X_mean
    X_test /= X_std
    X_valid -= X_mean
    X_valid /= X_std

    return X_train, X_test, X_valid

def standardize_data_with_std(y_train, y_test):
    y_mean = np.mean(y_train, axis=0)
    y_std = np.std(y_train, axis=0)

    y_train -= y_mean
    y_train /= y_std
    y_test -= y_mean
    y_test /= y_std
    
    return y_train, y_test, y_mean, y_std


def main():
    np.random.seed(1234)
    tf.set_random_seed(1237)

    dataset = np.loadtxt("traindata.txt", delimiter=",")

	 
    x_train = dataset[:,0:17]

    y_train = dataset[:,17]

    dataset = np.loadtxt("testdata.txt", delimiter=",")


    x_test_1 = dataset[:,0:17]

    y_test_1 = dataset[:,17]

    dataset = np.loadtxt("testdata.txt.en_de", delimiter=",")

    x_test_2 = dataset[:,0:17]

    y_test_2 = dataset[:,17]

    dataset = np.loadtxt("validdata.txt", delimiter=",")


    x_valid = dataset[:,0:17]

    y_valid = dataset[:,17]


    #data_path = os.path.join(conf.data_dir, 'housing.data')
    #x_train, y_train, x_valid, y_valid, x_test, y_test = \
    #    dataset.load_uci_boston_housing(data_path)
    N, n_x = x_train.shape

    print(N, n_x)

    #print(type(y_test))
    # Standardize data
    x_train_1, x_test_1, _, _ = standardize_data_with_std(copy.deepcopy(x_train), copy.deepcopy(x_test_1))

    x_train_2, x_test_2, _, _ = standardize_data_with_std(copy.deepcopy(x_train), copy.deepcopy(x_test_2))

    x_train_3, x_valid, _, _ = standardize_data_with_std(copy.deepcopy(x_train), copy.deepcopy(x_valid))

    #y_train_1, y_test_1, mean_y_train, std_y_train = standardize_data_with_std(copy.deepcopy(y_train), copy.deepcopy(y_test_1))

    #y_train_2, y_test_2, mean_y_train, std_y_train = standardize_data_with_std(copy.deepcopy(y_train), copy.deepcopy(y_test_2))

    #y_train_3, y_valid, _, _ = standardize_data_with_std(copy.deepcopy(y_train), copy.deepcopy(y_valid))

    #y_train = y_train_1
    x_train = x_train_1

    # Standardize data
    #x_train, x_test, _, _ = dataset.standardize(x_train, x_test)
    #y_train, y_test, mean_y_train, std_y_train = dataset.standardize(
    #    y_train.tolist(), y_test.tolist())

    # Define model parameters
    n_hiddens = [64]

    @zs.reuse('model')
    def bayesianNN(observed, x, n_x, layer_sizes, n_particles):
        with zs.BayesianNet(observed=observed) as model:
            ws = []
            for i, (n_in, n_out) in enumerate(zip(layer_sizes[:-1],
                                                  layer_sizes[1:])):
                w_mu = tf.zeros([1, n_out, n_in + 1])
                ws.append(
                    zs.Normal('w' + str(i), w_mu, std=1.,
                              n_samples=n_particles, group_ndims=2))

            # forward
            ly_x = tf.expand_dims(
                tf.tile(tf.expand_dims(x, 0), [n_particles, 1, 1]), 3)
            for i in range(len(ws)):
                w = tf.tile(ws[i], [1, tf.shape(x)[0], 1, 1])
                ly_x = tf.concat(
                    [ly_x, tf.ones([n_particles, tf.shape(x)[0], 1, 1])], 2)
                ly_x = tf.matmul(w, ly_x) / \
                    tf.sqrt(tf.to_float(tf.shape(ly_x)[2]))
                if i < len(ws) - 1:
                    ly_x = tf.nn.relu(ly_x)

            y_mean = tf.squeeze(ly_x, [2, 3])
            y_logstd = tf.get_variable('y_logstd', shape=[],
                                       initializer=tf.constant_initializer(0.))
            y = zs.Normal('y', y_mean, logstd=y_logstd)

        return model, y_mean

    def mean_field_variational(layer_sizes, n_particles):
        with zs.BayesianNet() as variational:
            ws = []
            for i, (n_in, n_out) in enumerate(zip(layer_sizes[:-1],
                                                  layer_sizes[1:])):
                w_mean = tf.get_variable(
                    'w_mean_' + str(i), shape=[1, n_out, n_in + 1],
                    initializer=tf.constant_initializer(0.))
                w_logstd = tf.get_variable(
                    'w_logstd_' + str(i), shape=[1, n_out, n_in + 1],
                    initializer=tf.constant_initializer(0.))
                ws.append(
                    zs.Normal('w' + str(i), w_mean, logstd=w_logstd,
                              n_samples=n_particles, group_ndims=2))
        return variational

    # Build the computation graph
    n_particles = tf.placeholder(tf.int32, shape=[], name='n_particles')
    x = tf.placeholder(tf.float32, shape=[None, n_x])
    y = tf.placeholder(tf.float32, shape=[None])
    layer_sizes = [n_x] + n_hiddens + [1]
    w_names = ['w' + str(i) for i in range(len(layer_sizes) - 1)]

    def log_joint(observed):
        model, _ = bayesianNN(observed, x, n_x, layer_sizes, n_particles)
        log_pws = model.local_log_prob(w_names)
        log_py_xw = model.local_log_prob('y')
        return tf.add_n(log_pws) + log_py_xw * N

    variational = mean_field_variational(layer_sizes, n_particles)
    qw_outputs = variational.query(w_names, outputs=True, local_log_prob=True)
    latent = dict(zip(w_names, qw_outputs))
    y_obs = tf.tile(tf.expand_dims(y, 0), [n_particles, 1])
    lower_bound = zs.variational.elbo(
        log_joint, observed={'y': y_obs}, latent=latent, axis=0)
    cost = tf.reduce_mean(lower_bound.sgvb())
    lower_bound = tf.reduce_mean(lower_bound)

    optimizer = tf.train.AdamOptimizer(learning_rate=0.01)
    infer_op = optimizer.minimize(cost)

    # prediction: rmse & log likelihood
    observed = dict((w_name, latent[w_name][0]) for w_name in w_names)
    observed.update({'y': y_obs})
    model, y_mean = bayesianNN(observed, x, n_x, layer_sizes, n_particles)
    y_pred = tf.reduce_mean(y_mean, 0)
    #rmse = tf.sqrt(tf.reduce_mean((y_pred - y) ** 2)) * std_y_train
    rmse = tf.sqrt(tf.reduce_mean((y_pred - y) ** 2))
    log_py_xw = model.local_log_prob('y')
 
    #values = tf.cast(std_y_train, dtype=tf.float32)

    #log_likelihood = tf.reduce_mean(zs.log_mean_exp(log_py_xw, 0)) - tf.log(values)
    log_likelihood = tf.reduce_mean(zs.log_mean_exp(log_py_xw, 0)) - 1

    # Define training/evaluation parameters
    lb_samples = 10
    ll_samples = 10
    epochs = 250
    batch_size = 128
    iters = int(np.floor(x_train.shape[0] / float(batch_size)))
    test_freq = 10

    # Run the inference
    with tf.Session() as sess:
        sess.run(tf.global_variables_initializer())
        for epoch in range(1, epochs + 1):
            lbs = []
            for t in range(iters):
                x_batch = x_train[t * batch_size:(t + 1) * batch_size]
                y_batch = y_train[t * batch_size:(t + 1) * batch_size]
                _, lb = sess.run(
                    [infer_op, lower_bound],
                    feed_dict={n_particles: lb_samples, x: x_batch, y: y_batch})
                lbs.append(lb)
            print('Epoch {}: Lower bound = {}'.format(epoch, np.mean(lbs)))

            if epoch % test_freq == 0:
                test_lb, test_rmse, test_ll = sess.run(
                    [lower_bound, rmse, log_likelihood],
                    feed_dict={n_particles: ll_samples,
                               x: x_test_1, y: y_test_1})
                print('>> TEST')
                print('>> lower bound = {}, rmse = {}, log_likelihood = {}'
                      .format(test_lb, test_rmse, test_ll))


                test_lb, test_rmse, test_ll = sess.run(
                    [lower_bound, rmse, log_likelihood],
                    feed_dict={n_particles: ll_samples,
                               x: x_test_2, y: y_test_2})
                print('>> TEST')
                print('>> lower bound = {}, rmse = {}, log_likelihood = {}'
                      .format(test_lb, test_rmse, test_ll))


                test_lb, test_rmse, test_ll = sess.run(
                    [lower_bound, rmse, log_likelihood],
                    feed_dict={n_particles: ll_samples,
                               x: x_valid, y: y_valid})
                print('>> VALID')
                print('>> lower bound = {}, rmse = {}, log_likelihood = {}'
                      .format(test_lb, test_rmse, test_ll))


if __name__ == '__main__':
    main()
