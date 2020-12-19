import numpy as np
import igraph as ig 
import csv
import pandas as pd
import os
from graspologic.simulations import sbm
from sklearn.covariance import GraphicalLassoCV
import matplotlib.pyplot as plt
import networkx as nx
from community import community_louvain
import umap
from plotnine import *


def load_adj(path):
    full_path = os.path.join(path, 'adj.txt')
    num_nodes = -1
    adj = []
    with open(full_path, mode='r') as txt_file:
        for row in txt_file:
            row = row.split(",")
            num_nodes += 1
            if num_nodes == 0:
                continue
            adj.append([float(row[i]) for i in range(0, len(row))])

    adj = np.asarray(adj)
    return adj, num_nodes


def load_classes(path, type, max_labels=None, **kwargs):
    full_path = os.path.join(path, 'classes_{type}.txt'.format(type=type))
    classes = pd.read_csv(full_path)
    nans = pd.isna(classes['class_']).values
    classes.dropna(axis=0, inplace=True)
    classes['id'] = pd.factorize(classes.class_)[0]
    labels = classes['id'].values
    labels -= (np.min(labels) - 1)
    # labels = classes['id'].values.astype(int)
    print(labels)
    if (max_labels is None) or max_labels >= np.max(labels):
        num_classes = np.max(labels)
        num_graphs = labels.shape[0]
        labels -= np.ones(shape=(num_graphs,), dtype=int)
        one_hot_labels = np.zeros((num_graphs, num_classes))
        one_hot_labels[np.arange(num_graphs), labels] = 1
        return labels, one_hot_labels, num_graphs, num_classes, nans
    else:
        num_classes = max_labels
        num_graphs = labels.shape[0]
        for_one_hot = np.where(labels <= max_labels, labels, 0)
        labels = np.where(labels <= max_labels, labels, max_labels + 1)
        labels -= np.ones(shape=(num_graphs,), dtype=int)
        one_hot_labels = np.zeros((num_graphs, num_classes))
        one_hot_labels[np.arange(num_graphs), for_one_hot] = 1
        return labels, one_hot_labels, num_graphs, max_labels + 1, nans


def load_features(path, type, is_binary=False, **kwargs):
    full_path = os.path.join(path, 'data_{type}.txt'.format(type=type))
    num_nodes = -1
    features = []
    with open(full_path, mode='r') as csv_file:
        csv_reader = csv.reader(csv_file)
        for row in csv_reader:
            num_nodes += 1
            if num_nodes == 0:
                continue
            if is_binary:
                features.append([1 if float(row[i]) > 0 else 0 for i in range(0, len(row))])
            else:
                features.append([float(row[i]) for i in range(0, len(row))])
    features = np.asarray(features)
    features = features.T
    return features


def gen_syn_data(
    n_classes=3,
    n_obs_train=200,
    n_obs_test=100,
    n_features=10,
    n_edges=3,
    n_char_features=10,
    signal=[10, 10],
    diff_coef=[0.1, 0.1],
    noise=[0.01, 0.01],
    n_communities=5,
    probs=[0.5, 0.1],
    n_iter=3,
    model='SBM',
    random_seed=1996):
    """
    Generates a dataset. 
    Each class is defined by a set of characteristic features. 
    Each feature starts with random values. For each observation, the characteristic features of its class are increased by "signal".
    Then, values on each node diffuse through the graph.
    Parameters:
    ----------
    n_classes: number of classes
    n_obs: number of observations per class
    n_features: number of features, each corresponding to a node in the graph
    n_char_features: number of features that are specific to each class
    signal: how much the value is increased for the characteristic features
    diff_coef: how much each value transmits its value to the next
    noise: noise level added at the end
    Returns:
    X: feature matrix
    y: labels
    graph: underlying graph
    """
    np.random.seed(random_seed)
    # Generate a scale-free graph with the Barabasi Albert model.
    if model=="BA":
        graph_train  = graph_test = ig.Graph.Barabasi(n_features, n_edges, directed=False)
        adj_train = adj_test = np.array(graph_train.get_adjacency().data)
    if model=='ER':
        graph_train = graph_test = ig.Graph.Erdos_Renyi(n=n_features, m=n_edges*n_features, directed=False)
        adj_train = adj_test = np.array(graph_train.get_adjacency().data)
    if model=='SBM':
        n = [n_features // n_communities] * n_communities
        p = np.full((n_communities, n_communities), probs[1])
        adj_train = sbm(n=n, p=p)
        adj_test  = sbm(n=n, p=p)
        graph_train = ig.Graph.Adjacency(adj_train.tolist())
        graph_test  = ig.Graph.Adjacency(adj_test.tolist())
    X_train = []
    y_train = []
    X_test  = []
    y_test  = []
    for c in range(n_classes):
        # Draw the features which define this class
        char_features = np.random.choice(n_features,size=n_char_features,replace=False)
        for i in range(n_obs_train):
            # Start from a random vector
            features = np.abs(np.random.normal(0, 1, n_features))
            # TODO: force features to be positive or accept negative features ?
            # Increase the value for the characteristic features
            features[char_features] += np.abs(np.random.normal(signal[0], 1, n_char_features))
            features = features / np.linalg.norm(features)
            # Diffuse values through the graph
            # TODO: add different edge labels (positive or negative regulation)
            # TODO: maybe also give a weight to each edge
            for i in range(n_iter):
                features_next = np.copy(features)
                for e in graph_train.es:
                    features_next[e.target]+= (features[e.source] - features[e.target]) * diff_coef[0]
                    features_next[e.source]+= (features[e.target] - features[e.source]) * diff_coef[0]
                features = features_next
            if noise[0] > 0:
                features += np.random.normal(0, noise[0], n_features)
            X_train.append(features)
            y_train.append(c)

        for i in range(n_obs_test):
            # Start from a random vector
            features = np.abs(np.random.normal(0, 1, n_features))
            # TODO: force features to be positive or accept negative features ?
            # Increase the value for the characteristic features
            features[char_features] += np.abs(np.random.normal(signal[1], 1, n_char_features))
            features = features / np.linalg.norm(features)
            # Diffuse values through the graph
            # TODO: add different edge labels (positive or negative regulation)
            # TODO: maybe also give a weight to each edge
            for i in range(n_iter):
                features_next = np.copy(features)
                for e in graph_test.es:
                    features_next[e.target]+= (features[e.source] - features[e.target]) * diff_coef[1]
                    features_next[e.source]+= (features[e.target] - features[e.source]) * diff_coef[1]
                features = features_next
            if noise[1] > 0:
                features += np.random.normal(0, noise[1], n_features)
            X_test.append(features)
            y_test.append(c)
    train_idx = np.random.permutation(len(y_train)) - 1
    X_train   = np.array(X_train)[train_idx, :]
    y_train   = np.array(y_train)[train_idx]
    test_idx  = np.random.permutation(len(y_test)) - 1
    X_test    = np.array(X_test)[test_idx, :]
    y_test    = np.array(y_test)[test_idx]

    return X_train, y_train, adj_train, \
        X_test, y_test, adj_test

def glasso(data, **kwargs):
    cov = GraphicalLassoCV(kwargs).fit(data)
    precision_matrix = cov.get_precision()
    adjacency_matrix = precision_matrix.astype(bool).astype(int)
    return adjacency_matrix

# def compare_graphs(A, Ah):
#     TP = np.sum(A[A==1] == Ah[A==1]) # true positive rate
#     TN = np.sum(A[A==0] == Ah[A==0]) # true negative rate
#     FP = np.sum(A[A==0] != Ah[A==0]) # false positive rate
#     FN = np.sum(A[A==1] != Ah[A==1]) # false negative rate
#     precision = TP / (TP + FP)
#     recall    = TP / (TP + FN)
#     f1_score  = 2 * precision * recall / (precision + recall)
#     return precision, recall, f1_score

def compare_graphs(A, Ah):
    a = A - Ah
    return np.sqrt(np.max(np.linalg.eigvals(np.inner(a, a))))


def community_layout(g, partition):
    """
    Compute the layout for a modular graph.


    Arguments:
    ----------
    g -- networkx.Graph or networkx.DiGraph instance
        graph to plot

    partition -- dict mapping int node -> int community
        graph partitions


    Returns:
    --------
    pos -- dict mapping int node -> (float x, float y)
        node positions

    """

    pos_communities = _position_communities(g, partition, scale=3.)

    pos_nodes = _position_nodes(g, partition, scale=1.)

    # combine positions
    pos = dict()
    for node in g.nodes():
        pos[node] = pos_communities[node] + pos_nodes[node]

    return pos

def _position_communities(g, partition, **kwargs):

    # create a weighted graph, in which each node corresponds to a community,
    # and each edge weight to the number of edges between communities
    between_community_edges = _find_between_community_edges(g, partition)

    communities = set(partition.values())
    hypergraph = nx.DiGraph()
    hypergraph.add_nodes_from(communities)
    for (ci, cj), edges in between_community_edges.items():
        hypergraph.add_edge(ci, cj, weight=len(edges))

    # find layout for communities
    pos_communities = nx.spring_layout(hypergraph, **kwargs)

    # set node positions to position of community
    pos = dict()
    for node, community in partition.items():
        pos[node] = pos_communities[community]

    return pos

def _find_between_community_edges(g, partition):

    edges = dict()

    for (ni, nj) in g.edges():
        ci = partition[ni]
        cj = partition[nj]

        if ci != cj:
            try:
                edges[(ci, cj)] += [(ni, nj)]
            except KeyError:
                edges[(ci, cj)] = [(ni, nj)]

    return edges

def _position_nodes(g, partition, **kwargs):
    """
    Positions nodes within communities.
    """

    communities = dict()
    for node, community in partition.items():
        try:
            communities[community] += [node]
        except KeyError:
            communities[community] = [node]

    pos = dict()
    for ci, nodes in communities.items():
        subgraph = g.subgraph(nodes)
        pos_subgraph = nx.spring_layout(subgraph, **kwargs)
        pos.update(pos_subgraph)

    return pos

def draw_graph(adjacency_matrix, node_color=None):
    rows, cols = np.where(adjacency_matrix == 1)
    edges = zip(rows.tolist(), cols.tolist())
    g = nx.Graph()
    g.add_edges_from(edges)
    partition = community_louvain.best_partition(g)
    pos = community_layout(g, partition)
    if node_color == None:
      node_color = list(partition.values())
    print(g.number_of_nodes())
    print(len(node_color))
    nx.draw(g, pos, node_color=node_color); 
    return list(partition.values())

def plot_lowDim(data, labels = 'NA', title=None):
    #TODO: add shape.
    reducer   = umap.UMAP()
    embedding = reducer.fit_transform(data)
    plt.scatter(embedding[:, 0], embedding[:, 1], c=labels, cmap='Spectral', s=5)
    plt.title(title, fontsize=24)