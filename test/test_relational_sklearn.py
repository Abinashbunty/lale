# Copyright 2021 IBM Corporation
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import re
import unittest

import jsonschema
import numpy as np
import pandas as pd
import sklearn
from sklearn.feature_selection import SelectKBest as SkSelectKBest
from sklearn.impute import SimpleImputer as SkSimpleImputer
from sklearn.pipeline import make_pipeline as sk_make_pipeline
from sklearn.preprocessing import MinMaxScaler as SkMinMaxScaler
from sklearn.preprocessing import OneHotEncoder as SkOneHotEncoder
from sklearn.preprocessing import OrdinalEncoder as SkOrdinalEncoder
from sklearn.preprocessing import StandardScaler as SkStandardScaler

import lale.datasets
import lale.datasets.openml
from lale.datasets import pandas2spark
from lale.datasets.data_schemas import (
    SparkDataFrameWithIndex,
    add_table_name,
    forward_metadata,
    get_index_name,
)
from lale.datasets.multitable.fetch_datasets import fetch_go_sales_dataset
from lale.expressions import it
from lale.helpers import _ensure_pandas
from lale.lib.lale import Scan, categorical
from lale.lib.rasl import Map
from lale.lib.rasl import MinMaxScaler as RaslMinMaxScaler
from lale.lib.rasl import OneHotEncoder as RaslOneHotEncoder
from lale.lib.rasl import OrdinalEncoder as RaslOrdinalEncoder
from lale.lib.rasl import PrioBatch, PrioStep
from lale.lib.rasl import SelectKBest as RaslSelectKBest
from lale.lib.rasl import SimpleImputer as RaslSimpleImputer
from lale.lib.rasl import StandardScaler as RaslStandardScaler
from lale.lib.rasl import fit_with_batches, mockup_data_loader
from lale.lib.sklearn import FunctionTransformer, LogisticRegression, SGDClassifier

assert sklearn.__version__ >= "1.0", sklearn.__version__


def _check_trained_min_max_scaler(test, op1, op2, msg):
    test.assertEqual(list(op1.data_min_), list(op2.data_min_), msg)
    test.assertEqual(list(op1.data_max_), list(op2.data_max_), msg)
    test.assertEqual(list(op1.data_range_), list(op2.data_range_), msg)
    test.assertEqual(list(op1.scale_), list(op2.scale_), msg)
    test.assertEqual(list(op1.min_), list(op2.min_), msg)
    test.assertEqual(op1.n_features_in_, op2.n_features_in_, msg)
    test.assertEqual(op1.n_samples_seen_, op2.n_samples_seen_, msg)


class TestMinMaxScaler(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        targets = ["pandas", "spark", "spark-with-index"]
        cls.tgt2datasets = {tgt: fetch_go_sales_dataset(tgt) for tgt in targets}

    def test_get_params(self):
        sk_scaler = SkMinMaxScaler()
        rasl_scaler = RaslMinMaxScaler()
        sk_params = sk_scaler.get_params()
        rasl_params = rasl_scaler.get_params()
        self.assertDictContainsSubset(sk_params, rasl_params)

    def test_error(self):
        with self.assertRaisesRegex(
            jsonschema.ValidationError,
            re.compile(r"MinMaxScaler\(copy=False\)", re.MULTILINE | re.DOTALL),
        ):
            _ = RaslMinMaxScaler(copy=False)
        with self.assertRaisesRegex(
            jsonschema.ValidationError,
            re.compile(r"MinMaxScaler\(clip=True\)", re.MULTILINE | re.DOTALL),
        ):
            _ = RaslMinMaxScaler(clip=True)

    def test_fit(self):
        columns = ["Product number", "Quantity", "Retailer code"]
        pandas_data = self.tgt2datasets["pandas"][0][columns]
        sk_scaler = SkMinMaxScaler()
        sk_trained = sk_scaler.fit(pandas_data)
        rasl_scaler = RaslMinMaxScaler()
        for tgt, go_sales in self.tgt2datasets.items():
            data = go_sales[0][columns]
            if tgt == "spark-with-index":
                data = SparkDataFrameWithIndex(data)
            rasl_trained = rasl_scaler.fit(data)
            _check_trained_min_max_scaler(self, sk_trained, rasl_trained.impl, "pandas")

    def test_transform(self):
        columns = ["Product number", "Quantity", "Retailer code"]
        pandas_data = self.tgt2datasets["pandas"][0][columns]
        sk_scaler = SkMinMaxScaler()
        sk_trained = sk_scaler.fit(pandas_data)
        sk_transformed = sk_trained.transform(pandas_data)
        rasl_scaler = RaslMinMaxScaler()
        for tgt, go_sales in self.tgt2datasets.items():
            data = go_sales[0][columns]
            if tgt == "spark-with-index":
                data = SparkDataFrameWithIndex(data)
            rasl_trained = rasl_scaler.fit(data)
            rasl_transformed = rasl_trained.transform(data)
            if tgt == "spark-with-index":
                self.assertEqual(get_index_name(rasl_transformed), "index")
            rasl_transformed = _ensure_pandas(rasl_transformed)
            self.assertAlmostEqual(sk_transformed[0, 0], rasl_transformed.iloc[0, 0])
            self.assertAlmostEqual(sk_transformed[0, 1], rasl_transformed.iloc[0, 1])
            self.assertAlmostEqual(sk_transformed[0, 2], rasl_transformed.iloc[0, 2])
            self.assertAlmostEqual(sk_transformed[10, 0], rasl_transformed.iloc[10, 0])
            self.assertAlmostEqual(sk_transformed[10, 1], rasl_transformed.iloc[10, 1])
            self.assertAlmostEqual(sk_transformed[10, 2], rasl_transformed.iloc[10, 2])
            self.assertAlmostEqual(sk_transformed[20, 0], rasl_transformed.iloc[20, 0])
            self.assertAlmostEqual(sk_transformed[20, 1], rasl_transformed.iloc[20, 1])
            self.assertAlmostEqual(sk_transformed[20, 2], rasl_transformed.iloc[20, 2])

    def test_fit_range(self):
        columns = ["Product number", "Quantity", "Retailer code"]
        pandas_data = self.tgt2datasets["pandas"][0][columns]
        sk_scaler = SkMinMaxScaler(feature_range=(-5, 5))
        sk_trained = sk_scaler.fit(pandas_data)
        for tgt, go_sales in self.tgt2datasets.items():
            data = go_sales[0][columns]
            if tgt == "spark-with-index":
                data = SparkDataFrameWithIndex(data)
            rasl_scaler = RaslMinMaxScaler(feature_range=(-5, 5))
            rasl_trained = rasl_scaler.fit(data)
            _check_trained_min_max_scaler(self, sk_trained, rasl_trained.impl, "pandas")

    def test_transform_range(self):
        columns = ["Product number", "Quantity", "Retailer code"]
        pandas_data = self.tgt2datasets["pandas"][0][columns]
        sk_scaler = SkMinMaxScaler(feature_range=(-5, 5))
        sk_trained = sk_scaler.fit(pandas_data)
        sk_transformed = sk_trained.transform(pandas_data)
        rasl_scaler = RaslMinMaxScaler(feature_range=(-5, 5))
        for tgt, go_sales in self.tgt2datasets.items():
            data = go_sales[0][columns]
            if tgt == "spark-with-index":
                data = SparkDataFrameWithIndex(data)
            rasl_trained = rasl_scaler.fit(data)
            rasl_transformed = rasl_trained.transform(data)
            rasl_transformed = _ensure_pandas(rasl_transformed)
            self.assertAlmostEqual(sk_transformed[0, 0], rasl_transformed.iloc[0, 0])
            self.assertAlmostEqual(sk_transformed[0, 1], rasl_transformed.iloc[0, 1])
            self.assertAlmostEqual(sk_transformed[0, 2], rasl_transformed.iloc[0, 2])
            self.assertAlmostEqual(sk_transformed[10, 0], rasl_transformed.iloc[10, 0])
            self.assertAlmostEqual(sk_transformed[10, 1], rasl_transformed.iloc[10, 1])
            self.assertAlmostEqual(sk_transformed[10, 2], rasl_transformed.iloc[10, 2])
            self.assertAlmostEqual(sk_transformed[20, 0], rasl_transformed.iloc[20, 0])
            self.assertAlmostEqual(sk_transformed[20, 1], rasl_transformed.iloc[20, 1])
            self.assertAlmostEqual(sk_transformed[20, 2], rasl_transformed.iloc[20, 2])

    def test_partial_fit(self):
        columns = ["Product number", "Quantity", "Retailer code"]
        data = self.tgt2datasets["pandas"][0][columns]
        for tgt in self.tgt2datasets.keys():
            sk_scaler = SkMinMaxScaler()
            rasl_scaler = RaslMinMaxScaler()
            for lower, upper in [[0, 10], [10, 100], [100, data.shape[0]]]:
                data_so_far = data[0:upper]
                data_delta = data[lower:upper]
                if tgt == "pandas":
                    pass
                elif tgt == "spark":
                    data_delta = pandas2spark(data_delta)
                elif tgt == "spark-with-index":
                    data_delta = pandas2spark(data_delta, add_index=True)
                else:
                    assert False
                sk_trained = sk_scaler.fit(data_so_far)
                rasl_trained = rasl_scaler.partial_fit(data_delta)
                _check_trained_min_max_scaler(self, sk_trained, rasl_trained.impl, tgt)


class TestPipeline(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from sklearn.datasets import load_iris
        from sklearn.model_selection import train_test_split

        targets = ["pandas", "spark", "spark-with-index"]
        cls.tgt2datasets = {tgt: {} for tgt in targets}

        def add_df(name, df):
            cls.tgt2datasets["pandas"][name] = df
            cls.tgt2datasets["spark"][name] = pandas2spark(df)
            cls.tgt2datasets["spark-with-index"][name] = pandas2spark(
                df, add_index=True
            )

        X, y = load_iris(as_frame=True, return_X_y=True)
        X_train, X_test, y_train, y_test = train_test_split(X, y)
        add_df("X_train", X_train)
        add_df("X_test", X_test)
        add_df("y_train", y_train)
        add_df("y_test", y_test)

    def test_pipeline(self):
        for tgt, datasets in self.tgt2datasets.items():
            X_train, X_test = (datasets["X_train"], datasets["X_test"])
            y_train = self.tgt2datasets["pandas"]["y_train"]
            pipeline = (
                RaslMinMaxScaler()
                >> FunctionTransformer(func=lambda X: _ensure_pandas(X))
                >> LogisticRegression()
            )
            trained = pipeline.fit(X_train, y_train)
            _ = trained.predict(X_test)


def _check_trained_ordinal_encoder(test, op1, op2, msg):
    test.assertEqual(list(op1.feature_names_in_), list(op2.feature_names_in_), msg)
    test.assertEqual(len(op1.categories_), len(op2.categories_), msg)
    for i in range(len(op1.categories_)):
        test.assertEqual(list(op1.categories_[i]), list(op2.categories_[i]), msg)


class TestSelectKBest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from sklearn.datasets import load_digits

        targets = ["pandas", "spark", "spark-with-index"]
        cls.tgt2datasets = {tgt: {} for tgt in targets}

        def add_df(name, df):
            cls.tgt2datasets["pandas"][name] = df
            cls.tgt2datasets["spark"][name] = pandas2spark(df)
            cls.tgt2datasets["spark-with-index"][name] = pandas2spark(
                df, add_index=True
            )

        X, y = load_digits(return_X_y=True, as_frame=True)
        X = add_table_name(X, "X")
        y = add_table_name(y, "y")
        add_df("X", X)
        add_df("y", y)

    def _check_trained(self, sk_trained, rasl_trained, msg=""):
        for i in range(len(sk_trained.scores_)):
            if not (
                np.isnan(sk_trained.scores_[i])
                and np.isnan(rasl_trained.impl.scores_[i])
            ):
                self.assertAlmostEqual(
                    sk_trained.scores_[i],
                    rasl_trained.impl.scores_[i],
                    msg=f"{msg}: {i}",
                )
            if not (
                np.isnan(sk_trained.pvalues_[i])
                and np.isnan(rasl_trained.impl.pvalues_[i])
            ):
                self.assertAlmostEqual(
                    sk_trained.pvalues_[i],
                    rasl_trained.impl.pvalues_[i],
                    msg=f"{msg}: {i}",
                )
        self.assertEqual(
            sk_trained.n_features_in_, rasl_trained.impl.n_features_in_, msg
        )

    def test_fit(self):
        sk_trainable = SkSelectKBest(k=20)
        X, y = self.tgt2datasets["pandas"]["X"], self.tgt2datasets["pandas"]["y"]
        sk_trained = sk_trainable.fit(X, y)
        rasl_trainable = RaslSelectKBest(k=20)
        for tgt, datasets in self.tgt2datasets.items():
            X, y = datasets["X"], datasets["y"]
            if tgt == "spark":
                with self.assertRaises(ValueError):
                    rasl_trained = rasl_trainable.fit(X, y)
            else:
                rasl_trained = rasl_trainable.fit(X, y)
                self._check_trained(sk_trained, rasl_trained, tgt)

    def test_transform(self):
        sk_trainable = SkSelectKBest(k=20)
        X, y = self.tgt2datasets["pandas"]["X"], self.tgt2datasets["pandas"]["y"]
        sk_trained = sk_trainable.fit(X, y)
        sk_transformed = sk_trained.transform(X)
        rasl_trainable = RaslSelectKBest(k=20)
        for tgt, datasets in self.tgt2datasets.items():
            X, y = datasets["X"], datasets["y"]
            if tgt == "spark":
                with self.assertRaises(ValueError):
                    rasl_trained = rasl_trainable.fit(X, y)
                continue
            rasl_trained = rasl_trainable.fit(X, y)
            rasl_transformed = rasl_trained.transform(X)
            self._check_trained(sk_trained, rasl_trained, tgt)
            rasl_transformed = _ensure_pandas(rasl_transformed)
            self.assertEqual(sk_transformed.shape, rasl_transformed.shape, tgt)
            for row_idx in range(sk_transformed.shape[0]):
                for col_idx in range(sk_transformed.shape[1]):
                    self.assertAlmostEqual(
                        sk_transformed[row_idx, col_idx],
                        rasl_transformed.iloc[row_idx, col_idx],
                        msg=(row_idx, col_idx),
                    )

    def test_partial_fit(self):
        rasl_trainable = RaslSelectKBest(k=20)
        X, y = self.tgt2datasets["pandas"]["X"], self.tgt2datasets["pandas"]["y"]
        for lower, upper in [[0, 100], [100, 200], [200, X.shape[0]]]:
            X_so_far, y_so_far = X[0:upper], y[0:upper]
            sk_trainable = SkSelectKBest(k=20)
            sk_trained = sk_trainable.fit(X_so_far, y_so_far)
            X_delta, y_delta = X[lower:upper], y[lower:upper]
            rasl_trained = rasl_trainable.partial_fit(X_delta, y_delta)
            self._check_trained(
                sk_trained, rasl_trained, f"lower: {lower}, upper: {upper}"
            )


class TestOrdinalEncoder(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        targets = ["pandas", "spark", "spark-with-index"]
        cls.tgt2gosales = {tgt: fetch_go_sales_dataset(tgt) for tgt in targets}
        cls.tgt2creditg = {
            tgt: lale.datasets.openml.fetch(
                "credit-g",
                "classification",
                preprocess=False,
                astype=tgt,
            )
            for tgt in targets
        }

    def _check_last_trained(self, op1, op2, msg):
        _check_trained_ordinal_encoder(
            self, op1.get_last().impl, op2.get_last().impl, msg
        )

    def test_fit(self):
        prefix = Scan(table=it.go_daily_sales) >> Map(
            columns={"retailer": it["Retailer code"], "method": it["Order method code"]}
        )
        encoder_args = {"handle_unknown": "use_encoded_value", "unknown_value": np.nan}
        rasl_trainable = prefix >> RaslOrdinalEncoder(**encoder_args)
        sk_trainable = prefix >> SkOrdinalEncoder(**encoder_args)
        sk_trained = sk_trainable.fit(self.tgt2gosales["pandas"])
        for tgt, datasets in self.tgt2gosales.items():
            rasl_trained = rasl_trainable.fit(datasets)
            self._check_last_trained(sk_trained, rasl_trained, tgt)

    def test_partial_fit(self):
        prefix = Scan(table=it.go_daily_sales) >> Map(
            columns={"retailer": it["Retailer code"], "method": it["Order method code"]}
        )
        pandas_data = prefix.transform(self.tgt2gosales["pandas"])
        encoder_args = {"handle_unknown": "use_encoded_value", "unknown_value": np.nan}
        for tgt in self.tgt2gosales.keys():
            rasl_op = RaslOrdinalEncoder(**encoder_args)
            for lower, upper in [[0, 10], [10, 100], [100, pandas_data.shape[0]]]:
                data_so_far = pandas_data[0:upper]
                sk_op = SkOrdinalEncoder(**encoder_args).fit(data_so_far)
                data_delta = pandas_data[lower:upper]
                if tgt == "pandas":
                    pass
                elif tgt == "spark":
                    data_delta = pandas2spark(data_delta)
                elif tgt == "spark-with-index":
                    data_delta = pandas2spark(data_delta, add_index=True)
                else:
                    assert False
                rasl_op = rasl_op.partial_fit(data_delta)
                _check_trained_ordinal_encoder(
                    self,
                    sk_op,
                    rasl_op.impl,
                    f"tgt {tgt}, lower {lower}, upper {upper}",
                )

    def test_transform(self):
        prefix = Scan(table=it.go_daily_sales) >> Map(
            columns={"retailer": it["Retailer code"], "method": it["Order method code"]}
        )
        encoder_args = {"handle_unknown": "use_encoded_value", "unknown_value": np.nan}
        rasl_trainable = prefix >> RaslOrdinalEncoder(**encoder_args)
        sk_trainable = prefix >> SkOrdinalEncoder(**encoder_args)
        sk_trained = sk_trainable.fit(self.tgt2gosales["pandas"])
        sk_transformed = sk_trained.transform(self.tgt2gosales["pandas"])
        for tgt, datasets in self.tgt2gosales.items():
            rasl_trained = rasl_trainable.fit(datasets)
            self._check_last_trained(sk_trained, rasl_trained, tgt)
            rasl_transformed = rasl_trained.transform(datasets)
            if tgt == "spark-with-index":
                self.assertEqual(get_index_name(rasl_transformed), "index")
            rasl_transformed = _ensure_pandas(rasl_transformed)
            self.assertEqual(sk_transformed.shape, rasl_transformed.shape, tgt)
            for row_idx in range(sk_transformed.shape[0]):
                for col_idx in range(sk_transformed.shape[1]):
                    self.assertEqual(
                        sk_transformed[row_idx, col_idx],
                        rasl_transformed.iloc[row_idx, col_idx],
                        (row_idx, col_idx, tgt),
                    )

    def test_predict(self):
        (train_X_pd, train_y_pd), (test_X_pd, test_y_pd) = self.tgt2creditg["pandas"]
        cat_columns = categorical()(train_X_pd)
        prefix = Map(columns={c: it[c] for c in cat_columns})
        to_pd = FunctionTransformer(func=lambda X: _ensure_pandas(X))
        lr = LogisticRegression()
        encoder_args = {"handle_unknown": "use_encoded_value", "unknown_value": -1}
        sk_trainable = prefix >> SkOrdinalEncoder(**encoder_args) >> lr
        sk_trained = sk_trainable.fit(train_X_pd, train_y_pd)
        sk_predicted = sk_trained.predict(test_X_pd)
        rasl_trainable = prefix >> RaslOrdinalEncoder(**encoder_args) >> to_pd >> lr
        for tgt, dataset in self.tgt2creditg.items():
            (train_X, train_y), (test_X, test_y) = dataset
            rasl_trained = rasl_trainable.fit(train_X, train_y)
            rasl_predicted = rasl_trained.predict(test_X)
            self.assertEqual(sk_predicted.shape, rasl_predicted.shape, tgt)
            self.assertEqual(sk_predicted.tolist(), rasl_predicted.tolist(), tgt)


def _check_trained_one_hot_encoder(test, op1, op2, msg):
    test.assertEqual(list(op1.feature_names_in_), list(op2.feature_names_in_), msg)
    test.assertEqual(len(op1.categories_), len(op2.categories_), msg)
    for i in range(len(op1.categories_)):
        test.assertEqual(list(op1.categories_[i]), list(op2.categories_[i]), msg)


class TestOneHotEncoder(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import typing
        from typing import Any, Dict

        targets = ["pandas", "spark", "spark-with-index"]
        cls.tgt2creditg = typing.cast(
            Dict[str, Any],
            {
                tgt: lale.datasets.openml.fetch(
                    "credit-g",
                    "classification",
                    preprocess=False,
                    astype=tgt,
                )
                for tgt in targets
            },
        )

    def _check_last_trained(self, op1, op2, msg):
        _check_trained_one_hot_encoder(
            self, op1.get_last().impl, op2.get_last().impl, msg
        )

    def test_fit(self):
        (train_X_pd, _), (_, _) = self.tgt2creditg["pandas"]
        cat_columns = categorical()(train_X_pd)
        prefix = Map(columns={c: it[c] for c in cat_columns})
        rasl_trainable = prefix >> RaslOneHotEncoder()
        sk_trainable = prefix >> SkOneHotEncoder()
        sk_trained = sk_trainable.fit(train_X_pd)
        for tgt, dataset in self.tgt2creditg.items():
            (train_X, train_y), (test_X, test_y) = dataset
            rasl_trained = rasl_trainable.fit(train_X)
            self._check_last_trained(sk_trained, rasl_trained, tgt)

    def test_partial_fit(self):
        (train_X_pd, _), (_, _) = self.tgt2creditg["pandas"]
        cat_columns = categorical()(train_X_pd)
        prefix = Map(columns={c: it[c] for c in cat_columns})
        for tgt in self.tgt2creditg.keys():
            rasl_pipe = prefix >> RaslOneHotEncoder()
            for lower, upper in [[0, 10], [10, 100], [100, train_X_pd.shape[0]]]:
                data_so_far = train_X_pd[0:upper]
                sk_pipe = prefix >> SkOrdinalEncoder()
                sk_pipe = sk_pipe.fit(data_so_far)
                data_delta = train_X_pd[lower:upper]
                if tgt == "pandas":
                    pass
                elif tgt == "spark":
                    data_delta = pandas2spark(data_delta)
                elif tgt == "spark-with-index":
                    data_delta = pandas2spark(data_delta, add_index=True)
                else:
                    assert False
                rasl_pipe = rasl_pipe.partial_fit(data_delta)
                self._check_last_trained(
                    sk_pipe,
                    rasl_pipe,
                    (tgt, lower, upper),
                )

    def test_transform(self):
        (train_X_pd, train_y_pd), (test_X_pd, test_y_pd) = self.tgt2creditg["pandas"]
        cat_columns = categorical()(train_X_pd)
        prefix = Map(columns={c: it[c] for c in cat_columns})
        rasl_trainable = prefix >> RaslOneHotEncoder(sparse=False)
        sk_trainable = prefix >> SkOneHotEncoder(sparse=False)
        sk_trained = sk_trainable.fit(train_X_pd)
        sk_transformed = sk_trained.transform(test_X_pd)
        for tgt, dataset in self.tgt2creditg.items():
            (train_X, train_y), (test_X, test_y) = dataset
            rasl_trained = rasl_trainable.fit(train_X)
            self._check_last_trained(sk_trained, rasl_trained, tgt)
            rasl_transformed = rasl_trained.transform(test_X)
            if tgt == "spark-with-index":
                self.assertEqual(get_index_name(rasl_transformed), "index")
            rasl_transformed = _ensure_pandas(rasl_transformed)
            self.assertEqual(sk_transformed.shape, rasl_transformed.shape, tgt)
            for row_idx in range(sk_transformed.shape[0]):
                for col_idx in range(sk_transformed.shape[1]):
                    self.assertEqual(
                        sk_transformed[row_idx, col_idx],
                        rasl_transformed.iloc[row_idx, col_idx],
                        (row_idx, col_idx, tgt),
                    )

    def test_predict(self):
        (train_X_pd, train_y_pd), (test_X_pd, test_y_pd) = self.tgt2creditg["pandas"]
        cat_columns = categorical()(train_X_pd)
        prefix = Map(columns={c: it[c] for c in cat_columns})
        to_pd = FunctionTransformer(func=lambda X: _ensure_pandas(X))
        lr = LogisticRegression()
        sk_trainable = prefix >> SkOneHotEncoder(sparse=False) >> lr
        sk_trained = sk_trainable.fit(train_X_pd, train_y_pd)
        sk_predicted = sk_trained.predict(test_X_pd)
        rasl_trainable = prefix >> RaslOneHotEncoder(sparse=False) >> to_pd >> lr
        for tgt, dataset in self.tgt2creditg.items():
            (train_X, train_y), (test_X, test_y) = dataset
            rasl_trained = rasl_trainable.fit(train_X, train_y)
            rasl_predicted = rasl_trained.predict(test_X)
            self.assertEqual(sk_predicted.shape, rasl_predicted.shape, tgt)
            self.assertEqual(sk_predicted.tolist(), rasl_predicted.tolist(), tgt)


class TestSimpleImputer(unittest.TestCase):
    def setUp(self):
        targets = ["pandas", "spark", "spark-with-index"]
        self.tgt2adult = {
            tgt: lale.datasets.openml.fetch(
                "adult",
                "classification",
                preprocess=False,
                astype=tgt,
            )
            for tgt in targets
        }

    def _fill_missing_value(self, col_name, value, missing_value):
        for tgt, datasets in self.tgt2adult.items():
            (train_X, train_y), (test_X, test_y) = datasets
            if tgt == "pandas":
                train_X.loc[
                    train_X[col_name] == value, col_name
                ] = missing_value  # type:ignore
                test_X.loc[
                    test_X[col_name] == value, col_name
                ] = missing_value  # type:ignore
            elif tgt.startswith("spark"):
                from pyspark.sql.functions import col, when

                train_X_new = train_X.withColumn(
                    col_name,
                    when(col(col_name) == value, missing_value).otherwise(
                        col(col_name)
                    ),
                )
                test_X_new = test_X.withColumn(
                    col_name,
                    when(col(col_name) == value, missing_value).otherwise(
                        col(col_name)
                    ),
                )
                train_X = forward_metadata(train_X, train_X_new)
                test_X = forward_metadata(test_X, test_X_new)
            else:
                assert False
            self.tgt2adult[tgt] = (train_X, train_y), (test_X, test_y)

    def test_fit_transform_numeric_nan_missing(self):
        self._fill_missing_value("age", 36.0, np.nan)
        num_columns = ["age", "fnlwgt", "education-num"]
        prefix = Map(columns={c: it[c] for c in num_columns})

        hyperparams = [
            {"strategy": "mean"},
            {"strategy": "median"},
            {"strategy": "most_frequent"},
            {"strategy": "constant", "fill_value": 99},
        ]
        for hyperparam in hyperparams:
            rasl_trainable = prefix >> RaslSimpleImputer(**hyperparam)
            sk_trainable = prefix >> SkSimpleImputer(**hyperparam)
            sk_trained = sk_trainable.fit(self.tgt2adult["pandas"][0][0])
            sk_transformed = sk_trained.transform(self.tgt2adult["pandas"][1][0])
            sk_statistics_ = sk_trained.steps[-1][1].impl.statistics_
            for tgt, dataset in self.tgt2adult.items():
                (train_X, _), (test_X, _) = dataset
                rasl_trained = rasl_trainable.fit(train_X)
                # test the fit succeeded.
                rasl_statistics_ = rasl_trained.steps[-1][1].impl.statistics_

                self.assertEqual(
                    len(sk_statistics_), len(rasl_statistics_), (hyperparam, tgt)
                )
                for i in range(sk_statistics_.shape[0]):
                    self.assertAlmostEqual(
                        sk_statistics_[i], rasl_statistics_[i], msg=(i, hyperparam, tgt)
                    )

                rasl_transformed = rasl_trained.transform(test_X)
                if tgt == "spark-with-index":
                    self.assertEqual(get_index_name(rasl_transformed), "index")
                rasl_transformed = _ensure_pandas(rasl_transformed)
                self.assertEqual(sk_transformed.shape, rasl_transformed.shape, tgt)
                for row_idx in range(sk_transformed.shape[0]):
                    for col_idx in range(sk_transformed.shape[1]):
                        self.assertAlmostEqual(
                            sk_transformed[row_idx, col_idx],
                            rasl_transformed.iloc[row_idx, col_idx],
                            msg=(row_idx, col_idx, tgt),
                        )

    def test_fit_transform_numeric_nonan_missing(self):
        self._fill_missing_value("age", 36.0, -1)
        num_columns = ["age", "fnlwgt", "education-num"]
        prefix = Map(columns={c: it[c] for c in num_columns})

        hyperparams = [
            {"strategy": "mean"},
            {"strategy": "median"},
            {"strategy": "most_frequent"},
            {"strategy": "constant", "fill_value": 99},
        ]
        for hyperparam in hyperparams:
            rasl_trainable = prefix >> RaslSimpleImputer(
                missing_values=-1, **hyperparam
            )
            sk_trainable = prefix >> SkSimpleImputer(missing_values=-1, **hyperparam)
            sk_trained = sk_trainable.fit(self.tgt2adult["pandas"][0][0])
            sk_transformed = sk_trained.transform(self.tgt2adult["pandas"][1][0])
            sk_statistics_ = sk_trained.get_last().impl.statistics_
            for tgt, dataset in self.tgt2adult.items():
                (train_X, _), (test_X, _) = dataset
                rasl_trained = rasl_trainable.fit(train_X)
                # test the fit succeeded.
                rasl_statistics_ = rasl_trained.get_last().impl.statistics_  # type: ignore
                self.assertEqual(len(sk_statistics_), len(rasl_statistics_), tgt)
                self.assertEqual(list(sk_statistics_), list(rasl_statistics_), tgt)

                rasl_transformed = rasl_trained.transform(test_X)
                if tgt == "spark-with-index":
                    self.assertEqual(get_index_name(rasl_transformed), "index")
                rasl_transformed = _ensure_pandas(rasl_transformed)
                self.assertEqual(sk_transformed.shape, rasl_transformed.shape, tgt)
                for row_idx in range(sk_transformed.shape[0]):
                    for col_idx in range(sk_transformed.shape[1]):
                        self.assertEqual(
                            sk_transformed[row_idx, col_idx],
                            rasl_transformed.iloc[row_idx, col_idx],
                            (row_idx, col_idx, tgt),
                        )

    def test_predict(self):
        self._fill_missing_value("age", 36.0, np.nan)
        (train_X_pd, train_y_pd), (test_X_pd, test_y_pd) = self.tgt2adult["pandas"]
        num_columns = ["age", "fnlwgt", "education-num"]
        prefix = Map(columns={c: it[c] for c in num_columns})
        to_pd = FunctionTransformer(
            func=lambda X: X if isinstance(X, pd.DataFrame) else X.toPandas()
        )
        lr = LogisticRegression()
        imputer_args = {"strategy": "mean"}
        sk_trainable = prefix >> SkSimpleImputer(**imputer_args) >> lr
        sk_trained = sk_trainable.fit(train_X_pd, train_y_pd)
        sk_predicted = sk_trained.predict(test_X_pd)
        rasl_trainable = prefix >> RaslSimpleImputer(**imputer_args) >> to_pd >> lr
        for tgt, dataset in self.tgt2adult.items():
            (train_X, train_y), (test_X, test_y) = dataset
            rasl_trained = rasl_trainable.fit(train_X, train_y)
            rasl_predicted = rasl_trained.predict(test_X)
            self.assertEqual(sk_predicted.shape, rasl_predicted.shape, tgt)
            self.assertEqual(sk_predicted.tolist(), rasl_predicted.tolist(), tgt)

    def test_invalid_datatype_strategy(self):
        sk_trainable = SkSimpleImputer()
        with self.assertRaises(ValueError):
            sk_trainable.fit(self.tgt2adult["pandas"][0][0])
        rasl_trainable = RaslSimpleImputer()
        for tgt, dataset in self.tgt2adult.items():
            (train_X, _), (_, _) = dataset
            if tgt.startswith("spark"):
                # Skip test because of timeout!
                continue
            with self.assertRaises(ValueError):
                _ = rasl_trainable.fit(train_X)

    def test_default_numeric_fill_value(self):
        self._fill_missing_value("age", 36.0, np.nan)
        num_columns = ["age", "fnlwgt", "education-num"]
        prefix = Map(columns={c: it[c] for c in num_columns})

        hyperparams = [{"strategy": "constant"}]
        for hyperparam in hyperparams:
            rasl_trainable = prefix >> RaslSimpleImputer(**hyperparam)
            sk_trainable = prefix >> SkSimpleImputer(**hyperparam)
            sk_trained = sk_trainable.fit(self.tgt2adult["pandas"][0][0])
            sk_transformed = sk_trained.transform(self.tgt2adult["pandas"][1][0])
            sk_statistics_ = sk_trained.steps[-1][1].impl.statistics_
            for tgt, dataset in self.tgt2adult.items():
                (train_X, _), (test_X, _) = dataset
                rasl_trained = rasl_trainable.fit(train_X)
                # test the fit succeeded.
                rasl_statistics_ = rasl_trained.steps[-1][1].impl.statistics_
                self.assertEqual(len(sk_statistics_), len(rasl_statistics_), tgt)
                self.assertEqual(list(sk_statistics_), list(rasl_statistics_), tgt)

                rasl_transformed = rasl_trained.transform(test_X)
                rasl_transformed = _ensure_pandas(rasl_transformed)
                self.assertEqual(sk_transformed.shape, rasl_transformed.shape, tgt)
                for row_idx in range(sk_transformed.shape[0]):
                    for col_idx in range(sk_transformed.shape[1]):
                        self.assertEqual(
                            sk_transformed[row_idx, col_idx],
                            rasl_transformed.iloc[row_idx, col_idx],
                            (row_idx, col_idx, tgt),
                        )

    def test_default_string_fill_value(self):
        self._fill_missing_value("education", "Prof-school", np.nan)

        str_columns = ["workclass", "education", "capital-gain"]
        prefix = Map(columns={c: it[c] for c in str_columns})

        hyperparams = [{"strategy": "constant"}]
        for hyperparam in hyperparams:
            rasl_trainable = prefix >> RaslSimpleImputer(**hyperparam)
            sk_trainable = prefix >> SkSimpleImputer(**hyperparam)
            sk_trained = sk_trainable.fit(self.tgt2adult["pandas"][0][0])
            sk_statistics_ = sk_trained.steps[-1][1].impl.statistics_
            for tgt, dataset in self.tgt2adult.items():
                (train_X, _), (test_X, _) = dataset
                rasl_trained = rasl_trainable.fit(train_X)
                # test the fit succeeded.
                rasl_statistics_ = rasl_trained.steps[-1][1].impl.statistics_
                self.assertEqual(len(sk_statistics_), len(rasl_statistics_), tgt)
                self.assertEqual(list(sk_statistics_), list(rasl_statistics_), tgt)

                rasl_transformed = rasl_trained.transform(test_X)
                rasl_transformed = _ensure_pandas(rasl_transformed)
                # Note that for this test case, the output of sklearn transform does not
                # match rasl transform. There is at least one row which has a None
                # value and pandas replace treats it as nan and replaces it.
                # Sklearn which uses numpy does not replace a None.
                # So we just test that `missing_value` is the default assigned.
                self.assertEqual(rasl_transformed.iloc[1, 1], "missing_value")

    def test_multiple_modes_numeric(self):
        # Sklearn SimpleImputer says: for strategy `most_frequent`,
        # if there is more than one such value, only the smallest is returned.
        data = [[1, 10], [2, 14], [3, 15], [4, 15], [5, 14], [6, np.nan]]
        df = pd.DataFrame(data, columns=["Id", "Age"])
        hyperparam = {"strategy": "most_frequent"}
        sk_trainable = SkSimpleImputer(**hyperparam)
        rasl_trainable = RaslSimpleImputer(**hyperparam)
        sk_trained = sk_trainable.fit(df)
        rasl_trained = rasl_trainable.fit(df)
        self.assertEqual(
            len(sk_trained.statistics_), len(rasl_trained.impl.statistics_), "pandas"
        )
        self.assertEqual([6, 15], list(rasl_trained.impl.statistics_), "pandas")
        from pyspark.sql import SparkSession

        spark = (
            SparkSession.builder.master("local[1]")
            .appName("test_relational_sklearn")
            .getOrCreate()
        )
        spark_df = spark.createDataFrame(df)  # type:ignore

        rasl_trained = rasl_trainable.fit(spark_df)
        self.assertEqual(
            len(sk_trained.statistics_), len(rasl_trained.impl.statistics_), "spark"
        )
        self.assertIn(rasl_trained.impl.statistics_[1], [14, 15])

    def test_multiple_modes_string(self):
        # Sklearn SimpleImputer says: for strategy `most_frequent`,
        # if there is more than one such value, only the smallest is returned.
        data = [
            ["a", "t"],
            ["b", "f"],
            ["b", "m"],
            ["c", "f"],
            ["c", "m"],
            ["f", "missing"],
        ]
        df = pd.DataFrame(data, columns=["Id", "Gender"])
        hyperparam = {"strategy": "most_frequent", "missing_values": "missing"}
        sk_trainable = SkSimpleImputer(**hyperparam)
        rasl_trainable = RaslSimpleImputer(**hyperparam)
        sk_trained = sk_trainable.fit(df)
        rasl_trained = rasl_trainable.fit(df)
        self.assertEqual(
            len(sk_trained.statistics_), len(rasl_trained.impl.statistics_), "pandas"
        )
        self.assertEqual(
            list(["c", "m"]), list(rasl_trained.impl.statistics_), "pandas"
        )

        from pyspark.sql import SparkSession

        spark = (
            SparkSession.builder.master("local[1]")
            .appName("test_relational_sklearn")
            .getOrCreate()
        )
        spark_df = spark.createDataFrame(df)  # type:ignore

        rasl_trained = rasl_trainable.fit(spark_df)
        self.assertEqual(
            len(sk_trained.statistics_), len(rasl_trained.impl.statistics_), "spark"
        )
        self.assertIn(rasl_trained.impl.statistics_[1], ["f", "m"])

    def test_valid_partial_fit(self):
        self._fill_missing_value("age", 36.0, -1)
        num_columns = ["age", "fnlwgt", "education-num"]
        prefix = Map(columns={c: it[c] for c in num_columns})

        hyperparams = [
            {"strategy": "mean"},
            {"strategy": "constant", "fill_value": 99},
        ]
        for hyperparam in hyperparams:
            rasl_trainable = prefix >> RaslSimpleImputer(
                missing_values=-1, **hyperparam
            )
            sk_trainable = prefix >> SkSimpleImputer(missing_values=-1, **hyperparam)
            sk_trained = sk_trainable.fit(self.tgt2adult["pandas"][0][0])
            sk_transformed = sk_trained.transform(self.tgt2adult["pandas"][1][0])
            sk_statistics_ = sk_trained.get_last().impl.statistics_
            (train_X, _), (test_X, _) = self.tgt2adult["pandas"]
            data1_pandas = train_X.iloc[:10]
            data2_pandas = train_X.iloc[10:100]
            data3_pandas = train_X.iloc[100:]
            test_X_pandas = test_X

            for tgt in self.tgt2adult.keys():
                if tgt == "pandas":
                    data1 = data1_pandas
                    data2 = data2_pandas
                    data3 = data3_pandas
                    test_X = test_X_pandas
                elif tgt.startswith("spark"):
                    add_index = tgt == "spark-with-index"
                    data1 = pandas2spark(data1_pandas, add_index)  # type:ignore
                    data2 = pandas2spark(data2_pandas, add_index)  # type:ignore
                    data3 = pandas2spark(data3_pandas, add_index)  # type:ignore
                    test_X = pandas2spark(test_X_pandas, add_index)  # type:ignore
                else:
                    assert False
                rasl_trainable = prefix >> RaslSimpleImputer(
                    missing_values=-1, **hyperparam
                )
                rasl_trained = rasl_trainable.partial_fit(data1)
                rasl_trained = rasl_trained.partial_fit(data2)
                rasl_trained = rasl_trained.partial_fit(data3)
                # test the fit succeeded.
                rasl_statistics_ = rasl_trained.get_last().impl.statistics_  # type: ignore

                self.assertEqual(len(sk_statistics_), len(rasl_statistics_), tgt)
                for i in range(len(sk_statistics_)):
                    self.assertEqual(sk_statistics_[i], rasl_statistics_[i])

                rasl_transformed = rasl_trained.transform(test_X)
                rasl_transformed = _ensure_pandas(rasl_transformed)
                self.assertEqual(sk_transformed.shape, rasl_transformed.shape, tgt)
                for row_idx in range(sk_transformed.shape[0]):
                    for col_idx in range(sk_transformed.shape[1]):
                        self.assertEqual(
                            sk_transformed[row_idx, col_idx],
                            rasl_transformed.iloc[row_idx, col_idx],
                            (row_idx, col_idx, tgt),
                        )

    def test_invalid_partial_fit(self):
        num_columns = ["age", "fnlwgt", "education-num"]
        prefix = Map(columns={c: it[c] for c in num_columns})

        hyperparams = [
            {"strategy": "median"},
            {"strategy": "most_frequent"},
        ]
        for hyperparam in hyperparams:
            rasl_trainable = prefix >> RaslSimpleImputer(
                missing_values=-1, **hyperparam
            )
            (train_X, _), (_, _) = self.tgt2adult["pandas"]
            with self.assertRaises(ValueError):
                _ = rasl_trainable.partial_fit(train_X)


def _check_trained_standard_scaler(test, op1, op2, msg):
    test.assertEqual(list(op1.feature_names_in_), list(op2.feature_names_in_), msg)
    test.assertEqual(op1.n_features_in_, op2.n_features_in_, msg)
    test.assertEqual(op1.n_samples_seen_, op2.n_samples_seen_, msg)
    if op1.mean_ is None:
        test.assertIsNone(op2.mean_, msg)
    else:
        test.assertIsNotNone(op2.mean_, msg)
        test.assertEqual(len(op1.mean_), len(op2.mean_), msg)
        for i in range(len(op1.mean_)):
            test.assertAlmostEqual(op1.mean_[i], op2.mean_[i], msg=msg)
    if op1.var_ is None:
        test.assertIsNone(op2.var_, msg)
    else:
        test.assertIsNotNone(op2.var_, msg)
        test.assertEqual(len(op1.var_), len(op2.var_), msg)
        for i in range(len(op1.var_)):
            test.assertAlmostEqual(op1.var_[i], op2.var_[i], msg=msg)
    if op1.scale_ is None:
        test.assertIsNone(op2.scale_, msg)
    else:
        test.assertIsNotNone(op2.scale_, msg)
        test.assertEqual(len(op1.scale_), len(op2.scale_), msg)
        for i in range(len(op1.scale_)):
            test.assertAlmostEqual(op1.scale_[i], op2.scale_[i], msg=msg)


class TestStandardScaler(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import typing
        from typing import Any, Dict

        targets = ["pandas", "spark", "spark-with-index"]
        cls.tgt2creditg = typing.cast(
            Dict[str, Any],
            {
                tgt: lale.datasets.openml.fetch(
                    "credit-g",
                    "classification",
                    preprocess=True,
                    astype=tgt,
                )
                for tgt in targets
            },
        )

    def test_fit(self):
        (train_X_pd, _), (_, _) = self.tgt2creditg["pandas"]
        sk_trainable = SkStandardScaler()
        sk_trained = sk_trainable.fit(train_X_pd)
        rasl_trainable = RaslStandardScaler()
        for tgt, dataset in self.tgt2creditg.items():
            (train_X, _), (_, _) = dataset
            rasl_trained = rasl_trainable.fit(train_X)
            _check_trained_standard_scaler(self, sk_trained, rasl_trained.impl, tgt)

    def test_partial_fit(self):
        (train_X_pd, _), (_, _) = self.tgt2creditg["pandas"]
        for tgt in self.tgt2creditg.keys():
            rasl_op = RaslStandardScaler()
            for lower, upper in [[0, 10], [10, 100], [100, train_X_pd.shape[0]]]:
                data_so_far = train_X_pd[0:upper]
                sk_op = SkStandardScaler()
                sk_op = sk_op.fit(data_so_far)
                data_delta = train_X_pd[lower:upper]
                if tgt == "pandas":
                    pass
                elif tgt == "spark":
                    data_delta = pandas2spark(data_delta)
                elif tgt == "spark-with-index":
                    data_delta = pandas2spark(data_delta, add_index=True)
                else:
                    assert False
                rasl_op = rasl_op.partial_fit(data_delta)
                _check_trained_standard_scaler(
                    self, sk_op, rasl_op.impl, (tgt, lower, upper)
                )

    def test_transform(self):
        (train_X_pd, _), (test_X_pd, _) = self.tgt2creditg["pandas"]
        sk_trainable = SkStandardScaler()
        sk_trained = sk_trainable.fit(train_X_pd)
        sk_transformed = sk_trained.transform(test_X_pd)
        rasl_trainable = RaslStandardScaler()
        for tgt, dataset in self.tgt2creditg.items():
            (train_X, _), (test_X, _) = dataset
            rasl_trained = rasl_trainable.fit(train_X)
            _check_trained_standard_scaler(self, sk_trained, rasl_trained.impl, tgt)
            rasl_transformed = rasl_trained.transform(test_X)
            if tgt == "spark-with-index":
                self.assertEqual(get_index_name(rasl_transformed), "index")
            rasl_transformed = _ensure_pandas(rasl_transformed)
            self.assertEqual(sk_transformed.shape, rasl_transformed.shape, tgt)
            for row_idx in range(sk_transformed.shape[0]):
                for col_idx in range(sk_transformed.shape[1]):
                    self.assertAlmostEqual(
                        sk_transformed[row_idx, col_idx],
                        rasl_transformed.iloc[row_idx, col_idx],
                        msg=(row_idx, col_idx, tgt),
                    )

    def test_predict(self):
        (train_X_pd, train_y_pd), (test_X_pd, test_y_pd) = self.tgt2creditg["pandas"]
        to_pd = FunctionTransformer(func=lambda X: _ensure_pandas(X))
        lr = LogisticRegression()
        sk_trainable = SkStandardScaler() >> lr
        sk_trained = sk_trainable.fit(train_X_pd, train_y_pd)
        sk_predicted = sk_trained.predict(test_X_pd)
        rasl_trainable = RaslStandardScaler() >> to_pd >> lr
        for tgt, dataset in self.tgt2creditg.items():
            (train_X, train_y), (test_X, test_y) = dataset
            rasl_trained = rasl_trainable.fit(train_X, train_y)
            rasl_predicted = rasl_trained.predict(test_X)
            self.assertEqual(sk_predicted.shape, rasl_predicted.shape, tgt)
            self.assertEqual(sk_predicted.tolist(), rasl_predicted.tolist(), tgt)


class TestTaskGraphs(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        (train_X, train_y), (test_X, test_y) = lale.datasets.openml.fetch(
            "credit-g", "classification", preprocess=False
        )
        cat_columns = categorical()(train_X)
        project = Map(columns={c: it[c] for c in cat_columns})
        train_X, test_X = project.transform(train_X), project.transform(test_X)
        cls.creditg = (train_X, train_y), (test_X, test_y)

    @classmethod
    def _make_sk_trainable(cls):
        return sk_make_pipeline(
            SkOrdinalEncoder(handle_unknown="use_encoded_value", unknown_value=-1),
            SkMinMaxScaler(),
            SGDClassifier(random_state=123),
        )

    @classmethod
    def _make_rasl_trainable(cls):
        return (
            RaslOrdinalEncoder(handle_unknown="use_encoded_value", unknown_value=-1)
            >> RaslMinMaxScaler()
            >> SGDClassifier(random_state=123)
        )

    def test_fit_no_batching(self):
        (train_X, train_y), _ = self.creditg
        sk_trainable = self._make_sk_trainable()
        sk_trained = sk_trainable.fit(train_X, train_y)
        rasl_trainable = self._make_rasl_trainable()
        rasl_trained = rasl_trainable.fit(train_X, train_y)
        _check_trained_ordinal_encoder(
            self, sk_trained.steps[0][1], rasl_trained.steps[0][1].impl, "pandas"
        )
        _check_trained_min_max_scaler(
            self, sk_trained.steps[1][1], rasl_trained.steps[1][1].impl, "pandas"
        )

    def test_fit_batching(self):
        (train_X, train_y), _ = self.creditg
        sk_trainable = self._make_sk_trainable()
        sk_trained = sk_trainable.fit(train_X, train_y)
        unique_class_labels = list(train_y.unique())
        for n_batches in [1, 3]:
            for prio in [PrioStep(), PrioBatch()]:
                batches = mockup_data_loader(train_X, train_y, n_batches)
                rasl_trainable = self._make_rasl_trainable()
                rasl_trained = fit_with_batches(
                    rasl_trainable,
                    batches,
                    n_batches,
                    unique_class_labels,
                    prio,
                    incremental=False,
                    verbose=0,
                )
                _check_trained_ordinal_encoder(
                    self,
                    sk_trained.steps[0][1],
                    rasl_trained.steps[0][1].impl,
                    (n_batches, type(prio)),
                )
                _check_trained_min_max_scaler(
                    self,
                    sk_trained.steps[1][1],
                    rasl_trained.steps[1][1].impl,
                    (n_batches, type(prio)),
                )