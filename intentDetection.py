# -*- coding: utf-8 -*-
"""
Created on Mon Feb 17 01:14:33 2020

@author: sabab
"""

import os
import math
import datetime
from tqdm import tqdm 
import pandas as pd
import numpy as np
import tensorflow as tf
from tensorflow import keras 

import bert 
from bert import BertModelLayer
from bert.loader import StockBertConfig, map_stock_config_to_params, load_stock_weights
from bert.tokenization.bert_tokenization import FullTokenizer
import seaborn as sns

from pylab import rcParams
import matplotlib.pyplot as plt
from matplotlib.ticker import MaxNLocator
from matplotlib import rc

from sklearn.metrics import confusion_matrix, classification_report

class IntentDetectionData:
  DATA_COLUMN = "text"
  LABEL_COLUMN = "intent"

  def __init__(self, train, test, tokenizer: FullTokenizer, classes, max_seq_len=192):
    self.tokenizer = tokenizer
    self.max_seq_len = 0
    self.classes = classes
    
    train, test = map(lambda df: df.reindex(df[IntentDetectionData.DATA_COLUMN].str.len().sort_values().index), [train, test])
    
    ((self.train_x, self.train_y), (self.test_x, self.test_y)) = map(self._prepare, [train, test])

    print("max seq_len", self.max_seq_len)
    self.max_seq_len = min(self.max_seq_len, max_seq_len)
    self.train_x, self.test_x = map(self._pad, [self.train_x, self.test_x])

  def _prepare(self, df):
    x, y = [], []
    
    for _, row in tqdm(df.iterrows()):
      text, label = row[IntentDetectionData.DATA_COLUMN], row[IntentDetectionData.LABEL_COLUMN]
      tokens = self.tokenizer.tokenize(text)
      tokens = ["[CLS]"] + tokens + ["[SEP]"]
      token_ids = self.tokenizer.convert_tokens_to_ids(tokens)
      self.max_seq_len = max(self.max_seq_len, len(token_ids))
      x.append(token_ids)
      y.append(self.classes.index(label))

    return np.array(x), np.array(y)

  def _pad(self, ids):
    x = []
    for input_ids in ids:
      input_ids = input_ids[:min(len(input_ids), self.max_seq_len - 2)]
      input_ids = input_ids + [0] * (self.max_seq_len - len(input_ids))
      x.append(np.array(input_ids))
    return np.array(x)


def create_model(max_seq_len, bert_config_file, bert_ckpt_file):
    with tf.io.gfile.GFile(bert_config_file, 'r') as reader:
        bc = StockBertConfig.from_json_string(reader.read())
    bert_params = map_stock_config_to_params(bc)
    bert_params.adapter_size = None
    bert = BertModelLayer.from_params(bert_params, name = 'bert')
    
    input_ids = keras.layers.Input(shape = (max_seq_len, ), dtype='int32', name='input_ids')
    bert_output = bert(input_ids)
    
    print('bert_shape', bert_output.shape)
    
    cls_out = keras.layers.Lambda(lambda seq: seq[:,0,:]) (bert_output)
    cls_out = keras.layers.Dropout(0.5)(cls_out)
    logits = keras.layers.Dense(units=768, activation='tanh')(cls_out)
    logits = keras.layers.Dropout(0.5)(logits)
    logits = keras.layers.Dense(units=len(classes), activation='softmax')(cls_out)
    
    model = keras.Model(inputs = input_ids, outputs= logits)
    model.build(input_shape=(None, max_seq_len))
    
    load_stock_weights(bert, bert_ckpt_file)
    
    return model

def plot_graphs(f, history, string):
    plt.plot(history.history[string])
    plt.plot(history.history['val_'+string])
    plt.xlabel("Epochs")
    plt.ylabel(string)
    plt.legend([string, 'val_'+string])
    plt.show()


RANDOM_SEED = 42
lr = 0.000010
np.random.seed(RANDOM_SEED)
tf.random.set_seed(RANDOM_SEED)

train = pd.read_csv("train.csv")
valid = pd.read_csv("valid.csv")
test = pd.read_csv("test.csv")

train = train.append(valid).reset_index(drop=True)

# =============================================================================
# # plot classes to check the distribution
# chart = sns.countplot(train.intent, palette=HAPPY_COLORS_PALETTE)
# plt.title("Number of examples per intent")
# chart.set_xticklabels(chart.get_xticklabels(), rotation = 30, horizontalalignment= 'right')
# =============================================================================

#bert pretrained model weights and configuration file
bert_model_name = 'uncased_L-12_H-768_A-12'
bert_ckpt_dir = os.path.join('model/', bert_model_name)
bert_ckpt_file = os.path.join(bert_ckpt_dir, 'bert_model.ckpt')
bert_config_file = os.path.join(bert_ckpt_dir, 'bert_config.json')
tokenizer = FullTokenizer(vocab_file= os.path.join(bert_ckpt_dir, 'vocab.txt'))


classes = train.intent.unique().tolist()

data = IntentDetectionData(train, test, tokenizer, classes, max_seq_len=128)
model = create_model(data.max_seq_len, bert_config_file, bert_ckpt_file)

model.summary()

model.compile(
    optimizer = keras.optimizers.Adam(lr),
    loss = keras.losses.SparseCategoricalCrossentropy(from_logits=True),
    metrics = [keras.metrics.SparseCategoricalAccuracy(name='acc')]
)


history = model.fit(
    x = data.train_x,
    y = data.train_y,
    validation_split = 0.1,
    batch_size = 16,
    shuffle = True,
    epochs = 5
#    callbacks=[tensorboard_callback]
)

f1 = plt.figure()
plot_graphs(f1,history, "acc")
f2 = plt.figure()
plot_graphs(f2,history, "loss")



_, test_acc = model.evaluate(data.test_x, data.test_y)
y_pred = model.predict(data.test_x).argmax(axis=-1)
print(classification_report(data.test_y, y_pred, target_names = classes))
