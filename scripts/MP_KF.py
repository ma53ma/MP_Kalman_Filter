#!/usr/bin/env python
#import matplotlib
#matplotlib.use('Agg')
import rospy
import numpy as np
import time
import copy

import matplotlib.pyplot as plt
from sensor_msgs.msg import LaserScan, Imu
from nav_msgs.msg import Odometry
from geometry_msgs.msg import Point, Twist

from odom_set import odom_set

first_call = True
x = 0.0
y = 0.0
theta = 0.0

# do I need to change these?
theta_0 = 0.0
x_0 = 0.0
y_0 = 0.0

dist_thresh = np.inf

# cartesisan state of system-target relatives is:
# [v_x, v_y, r_x, r_y]

# modified polar state of system-target relatives is:
# [beta_dot, r_dot / r, beta, 1 / r]
# initial guess
y_kmin1_kmin1 = np.array([[0.0], [0.0], [np.pi/4], [1.0]], dtype=float)
P_kmin1_kmin1 = np.array([[1.0, 0.0, 0.0, 0.0],
                          [0.0, 1.0, 0.0, 0.0],
                          [0.0, 0.0, 1.0, 0.0],
                          [0.0, 0.0, 0.0, 1.0]], dtype=float)

# t0 = (k - 1) * T, T is sampling rate
t0 = time.time()

# tracking own acceleration between t0 and t
a_ox = np.array([], dtype=float)
a_oy = np.array([], dtype=float)

# question to answer: is this just a single value, or are these updates all at the same rate?

H = np.array([[0, 0, 1, 0]], dtype=float)

R = 0.05
first = True

def odom_callback(odom_msg):
    global x, y, theta, first_call
    x, y, theta, first_call = odom_set(odom_msg, first_call, theta_0, x_0, y_0)


# we are assuming a constant velocity of the object
def imu_callback(imu_msg):
    global a_ox, a_oy
    a_ox = np.append(a_ox, imu_msg.linear_acceleration.x)
    a_oy = np.append(a_oy, imu_msg.linear_acceleration.y)

# computating the own-acceleration terms, these are treated as noise in this problem
def compute_accels(a_ox, a_oy, t0, t):
    x_tspan = np.linspace(t0, t, len(a_ox))
    y_tspan = np.linspace(t0, t, len(a_oy))

    #rospy.loginfo('x_tspan size: {0}'.format(np.shape(x_tspan)))
    #rospy.loginfo('y_tspan size: {0}'.format(np.shape(y_tspan)))

    #rospy.loginfo('a_ox size: {0}'.format(np.shape(a_ox)))
    #rospy.loginfo('a_oy size: {0}'.format(np.shape(a_oy)))

    w_o1 = np.trapz(a_ox, x_tspan)
    w_o2 = np.trapz(a_oy, y_tspan)
    w_o3 = np.trapz((t - x_tspan)*a_ox, x_tspan)
    w_o4 = np.trapz((t - y_tspan)*a_oy, y_tspan)
    #rospy.loginfo('w_o1: {0}'.format(w_o1))
    #rospy.loginfo('w_o2: {0}'.format(w_o2))

    #rospy.loginfo('w_o3: {0}'.format(w_o3))
    #rospy.loginfo('w_o4: {0}'.format(w_o4))
    w = -np.array([[w_o1], [w_o2], [w_o3], [w_o4]], dtype=float)

    return w

# change of coordinates from MP to Cartesian
def fx_operator(y_t):
    # rospy.loginfo('y_t: {0}'.format(y_t[3]))
    y1 = y_t[0][0]
    y2 = y_t[1][0]
    y3 = y_t[2][0]
    y4 = y_t[3][0]
    # rospy.loginfo('{0}'.format(1 / y4))
    fx_y_t = np.divide(np.array([[y2*np.sin(y3) + y1*np.cos(y3)],
                                 [y2*np.cos(y3) - y1*np.sin(y3)],
                                 [np.sin(y3)],
                                 [np.cos(y3)]], dtype=float), (1 / y4))
    return fx_y_t

# change of coordinates from Cartesian to MP
def fy_operator(x_t):
    # rospy.loginfo('x_t: {0}'.format(x_t))

    x1 = x_t[0][0]
    x2 = x_t[1][0]
    x3 = x_t[2][0]
    x4 = x_t[3][0]
    #rospy.loginfo('x3: {0}'.format(x3))
    #rospy.loginfo('x4: {0}'.format(x4))

    fy_x_t = np.array([[(x1*x4 - x2*x3) / (x3**2 + x4**2)],
              [(x1*x3 + x2*x4) / (x3**2 + x4**2)],
              [np.arctan2(x3, x4)],
              [1 / np.sqrt(x3**2 + x4**2)]], dtype=float)

    return fy_x_t

def compute_A_y(y_k_kmin1, y_kmin1_kmin1):
    #rospy.loginfo('y_k_kmin1: {0}'.format(y_k_kmin1))
    #rospy.loginfo('y_kmin1_kmin1: {0}'.format(y_kmin1_kmin1))
    row_length = np.shape(y_k_kmin1)[0]
    y_kmin1_kmin1 = np.array(y_kmin1_kmin1, dtype=float).flatten()
    A_y = []
    for i in range(0, row_length):
        y_k_kmin1_i = y_k_kmin1[i]
        #rospy.loginfo('y_k_kmin1_i: {0}'.format(y_k_kmin1_i))
        y_k_kmin1_i_row = np.repeat(y_k_kmin1_i, row_length)
        #rospy.loginfo('y_k_kmin1_i_row: {0}'.format(y_k_kmin1_i_row))
        # rospy.loginfo('y_kmin1_kmin1: {0}'.format(y_kmin1_kmin1))
        y_k_kmin1_i_grad = np.gradient(np.array([y_kmin1_kmin1, y_k_kmin1_i_row], dtype=float), axis=0)
        #rospy.loginfo('y_k_kmin1_i_grad[0]: {0}'.format(y_k_kmin1_i_grad[0]))
        A_y.append(y_k_kmin1_i_grad[0])
    # rospy.loginfo('A_y size: {0}'.format(np.shape(A_y)))
    return A_y


def kf_update_loop(y_t):
    global first, a_ox, a_oy, t0, y_kmin1_kmin1, P_kmin1_kmin1
    t = time.time()

    # calculate accelerative noise
    w = compute_accels(copy.deepcopy(a_ox), copy.deepcopy(a_oy), t0, t)
    # rospy.loginfo('w: {0}'.format(w))
    A_x_t_t0 = [[1, 0, 0, 0],
                [0, 0, 0, 0],
                [t - t0, 0, 1, 0],
                [0, t - t0, 0, 1]]
    # Calculating y( K / K - 1), state estimate step
    fx_y_t0 = fx_operator(y_kmin1_kmin1)
    rospy.loginfo('fx_y_t0: {0}'.format(fx_y_t0))
    x_t = np.matmul(A_x_t_t0, fx_y_t0) + w
    rospy.loginfo('x_t: {0}'.format(x_t))
    y_k_kmin1 = fy_operator(x_t)

    # Calculating A_y estimate, A matrix for MP coordinates
    A_y = compute_A_y(y_k_kmin1, y_kmin1_kmin1)
    rospy.loginfo('A_y: {0}'.format(A_y))

    # Calculating covariance matrix estimate
    P_k_kmin1 = np.matmul(np.matmul(A_y, P_kmin1_kmin1), np.transpose(A_y, (0, 1)))

    # Calculating Kalman gain
    H_tranpose = np.transpose(H)
    #rospy.loginfo('P_k_kmin1 size: {0}'.format(np.shape(P_k_kmin1)))
    #rospy.loginfo('H_transpose size: {0}'.format(np.shape(H_tranpose)))
    #rospy.loginfo('H_transpose : {0}'.format(H_tranpose))

    pt1 = np.matmul(P_k_kmin1, H_tranpose)
    pt2 = np.matmul(np.matmul(H, P_k_kmin1), H_tranpose)
    pt3 = np.random.normal(loc=0, scale=R, size=1)

    #rospy.loginfo('pt1 size: {0}'.format(np.shape(pt1)))
    #rospy.loginfo('pt2 size: {0}'.format(np.shape(pt2)))
    #rospy.loginfo('pt3 size: {0}'.format(np.shape(pt3)))

    G_k = pt1 * np.linalg.inv(pt2 + pt3)

    # Calculating the state update
    beta_tilde_k = np.matmul(H, y_t) + pt3
    y_k_k = y_k_kmin1 + G_k * (beta_tilde_k - np.matmul(H, y_k_kmin1))


    # rospy.loginfo('G_k: {0}'.format(G_k))

    # Calculating the covariance update
    rospy.loginfo('H: {0}'.format(H))
    rospy.loginfo('G: {0}'.format(G_k))
    rospy.loginfo('P_k_kmin1: {0}'.format(P_k_kmin1))

    P_k_k = (np.eye(4) - G_k*H) * P_k_kmin1
    rospy.loginfo('P_k_k: {0}'.format(P_k_k))

    # setting old estimates equal to new estimates
    y_kmin1_kmin1 = y_k_k
    P_kmin1_kmin1 = P_k_k
    if first:
        plt.figure(figsize=(15, 4))
    ax1 = plt.subplot(121)
    plt.title('Bearing comparison')
    plt.scatter(t, y_k_kmin1[2], c='r', marker='o', label='Bearing estimate')
    plt.scatter(t, beta_tilde_k, c='k', marker='^', label='Bearing measurement')
    plt.ylim([-3.25, 3.25])
    plt.xlim([t - 5, t + 5])
    #@ax1.legend('Prediction', 'Sensor')
    if first:
        ax1.legend(loc="upper right")
    ax2 = plt.subplot(122)
    plt.title('Reciprocal range comparison')
    plt.scatter(t, y_k_kmin1[3], c='r', marker='o', label='Reciprocal range estimate')
    plt.scatter(t, y_t[3], c='k', marker='^', label='Reciprocal range measurement')
    plt.ylim([0, 4.0])
    plt.xlim([t - 5, t + 5])
    if first:
        ax2.legend(loc="upper right")
        first = False
    plt.draw()
    plt.pause(0.0000001)
    # resetting accelerations

    a_ox = np.array([], dtype=float)
    a_oy = np.array([], dtype=float)
    t0 = t

def scan_callback(scan_msg):
    global a_ox, a_oy, t0, P_kmin1_kmin1, y_kmin1_kmin1

    # cluster object
    objs_bearing_cluster = []
    objs_range_cluster = []
    obj_bearing_cluster = []
    obj_range_cluster = []
    for deg_i in range(1,len(scan_msg.ranges)):
        dist_i = scan_msg.ranges[deg_i]
        rad_i = deg_i * np.pi / 180
        dist_diff = np.abs(scan_msg.ranges[deg_i] - scan_msg.ranges[deg_i - 1])
        if dist_i < dist_thresh and dist_diff < 0.3:
            obj_range_cluster.append(dist_i)
            obj_bearing_cluster.append(rad_i)
        else:
            if len(obj_bearing_cluster) > 0:
                objs_bearing_cluster.append(obj_bearing_cluster)
                objs_range_cluster.append(obj_range_cluster)
                break
                #obj_bearing_cluster = []
                #obj_range_cluster = []
    rospy.loginfo('objs_bearing_cluster size: {0}'.format(np.shape(objs_bearing_cluster)))
    #print('obj_bearing_cluster: ', obj_bearing_cluster)
    #print('obj_range_cluster: ', obj_range_cluster)

    obj_range = np.mean(objs_range_cluster[0])
    obj_bearing = np.mean(objs_bearing_cluster[0])
    robot_to_world_T = [[np.cos(theta), -np.sin(theta), x],
                        [np.sin(theta), np.cos(theta), y],
                        [0, 0, 1]]

    lidar_pt_x = obj_range * np.cos(obj_bearing)  # IN LIDAR FRAME
    lidar_pt_y = obj_range * np.sin(obj_bearing)  # IN LIDAR FRAME

    lidar_pt = [[lidar_pt_x], [lidar_pt_y], [1]]
    world_pt = np.matmul(robot_to_world_T, lidar_pt)

    lidar_endpoint = np.array([world_pt[0][0], world_pt[1][0]])
    # here, bearing ranges from -pi to pi
    y_t = np.array([0.0, 0.0, np.arctan2(lidar_pt_x, lidar_pt_y), 1.0 / obj_range], dtype=float)
    kf_update_loop(y_t)
    #print('object point: ', lidar_endpoint)

## return relative position
## return relative velocity

def MP_KF():
    rospy.init_node('plot_lidar', anonymous=True)
    # plt.figure(figsize=(15, 5))
    odom_sub = rospy.Subscriber('/odom', Odometry, odom_callback, queue_size=3, buff_size=2**24)
    imu_sub = rospy.Subscriber('/imu', Imu, imu_callback, queue_size=3, buff_size=2**24)
    scan_sub = rospy.Subscriber('/scan', LaserScan, scan_callback, queue_size=1, buff_size=2**24)
    plt.ion()
    plt.show()
    # spin() simply keeps python from exiting until this node is stopped
    rospy.spin()

if __name__ == '__main__':
    MP_KF()

