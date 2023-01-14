# Copyright 2019 IBM Corporation
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

import pandas as pd
from packaging import version
from sklearn.ensemble import BaggingRegressor as SKLModel

import lale.docstrings
import lale.operators

from ._common_schemas import schema_1D_numbers, schema_X_numbers
from .function_transformer import FunctionTransformer


class _BaggingRegressorImpl:
    def __init__(self, **hyperparams):
        self._wrapped_model = SKLModel(**hyperparams)
        self._hyperparams = hyperparams

    def _get_estimator_param_name(self):
        be = self._hyperparams.get("base_estimator", "deprecated")
        if be is None or be == "deprecated":
            return "estimator"
        else:
            return "base_estimator"

    def get_params(self, deep=True):
        out = self._wrapped_model.get_params(deep=deep)
        # we want to return the lale operator, not the underlying impl
        est_name = self._get_estimator_param_name()
        out[est_name] = self._hyperparams[est_name]
        return out

    def fit(self, X, y, sample_weight=None):
        if isinstance(X, pd.DataFrame):
            feature_transformer = FunctionTransformer(
                func=lambda X_prime: pd.DataFrame(X_prime, columns=X.columns),
                inverse_func=None,
                check_inverse=False,
            )

            est_name = self._get_estimator_param_name()
            self._hyperparams[est_name] = (
                feature_transformer >> self._hyperparams[est_name]
            )
            self._wrapped_model = SKLModel(**self._hyperparams)
        self._wrapped_model.fit(X, y, sample_weight)

        return self

    def predict(self, X, **predict_params):
        return self._wrapped_model.predict(X, **predict_params)

    def score(self, X, y, sample_weight=None):
        return self._wrapped_model.score(X, y, sample_weight)


_hyperparams_schema = {
    "description": "A Bagging regressor.",
    "allOf": [
        {
            "type": "object",
            "required": [
                "base_estimator",
                "n_estimators",
                "max_samples",
                "max_features",
                "bootstrap",
                "bootstrap_features",
                "oob_score",
                "warm_start",
                "n_jobs",
                "random_state",
                "verbose",
            ],
            "relevantToOptimizer": ["n_estimators", "bootstrap"],
            "additionalProperties": False,
            "properties": {
                "base_estimator": {
                    "anyOf": [
                        {"laleType": "operator"},
                        {"enum": [None], "description": "DecisionTreeRegressor"},
                    ],
                    "default": None,
                    "description": "The base estimator to fit on random subsets of the dataset.",
                },
                "n_estimators": {
                    "type": "integer",
                    "minimumForOptimizer": 10,
                    "maximumForOptimizer": 100,
                    "distribution": "uniform",
                    "default": 10,
                    "description": "The number of base estimators in the ensemble.",
                },
                "max_samples": {
                    "description": "The number of samples to draw from X to train each base estimator.",
                    "anyOf": [
                        {
                            "description": "Draw max_samples samples.",
                            "type": "integer",
                            "minimum": 2,
                            "laleMaximum": "X/maxItems",  # number of rows
                            "forOptimizer": False,
                        },
                        {
                            "description": "Draw max_samples * X.shape[0] samples.",
                            "type": "number",
                            "minimum": 0.0,
                            "exclusiveMinimum": True,
                            "maximum": 1.0,
                        },
                    ],
                    "default": 1.0,
                },
                "max_features": {
                    "description": "The number of features to draw from X to train each base estimator.",
                    "anyOf": [
                        {
                            "description": "Draw max_features features.",
                            "type": "integer",
                            "minimum": 2,
                            "laleMaximum": "X/items/maxItems",  # number of columns
                            "forOptimizer": False,
                        },
                        {
                            "description": "Draw max_samples * X.shape[1] features.",
                            "type": "number",
                            "minimum": 0.0,
                            "exclusiveMinimum": True,
                            "maximum": 1.0,
                        },
                    ],
                    "default": 1.0,
                },
                "bootstrap": {
                    "type": "boolean",
                    "default": True,
                    "description": "Whether samples are drawn with (True) or without (False) replacement.",
                },
                "bootstrap_features": {
                    "type": "boolean",
                    "default": False,
                    "description": "Whether features are drawn with (True) or wrhout (False) replacement.",
                },
                "oob_score": {
                    "type": "boolean",
                    "default": False,
                    "description": "Whether to use out-of-bag samples to estimate the generalization error.",
                },
                "warm_start": {
                    "type": "boolean",
                    "default": False,
                    "description": "When set to True, reuse the solution of the previous call to fit and add more estimators to the ensemble, otherwise, just fit a whole new ensemble.",
                },
                "n_jobs": {
                    "description": "The number of jobs to run in parallel for both `fit` and `predict`.",
                    "anyOf": [
                        {
                            "description": "1 unless in joblib.parallel_backend context.",
                            "enum": [None],
                        },
                        {"description": "Use all processors.", "enum": [-1]},
                        {
                            "description": "Number of CPU cores.",
                            "type": "integer",
                            "minimum": 1,
                        },
                    ],
                    "default": None,
                },
                "random_state": {
                    "anyOf": [
                        {"type": "integer"},
                        {"laleType": "numpy.random.RandomState"},
                        {"enum": [None]},
                    ],
                    "default": None,
                    "description": "If int, random_state is the seed used by the random number generator;",
                },
                "verbose": {
                    "type": "integer",
                    "default": 0,
                    "description": "Controls the verbosity when fitting and predicting.",
                },
            },
        },
        {
            "description": "Out of bag estimation only available if bootstrap=True",
            "anyOf": [
                {"type": "object", "properties": {"bootstrap": {"enum": [True]}}},
                {"type": "object", "properties": {"oob_score": {"enum": [False]}}},
            ],
        },
        {
            "description": "Out of bag estimate only available if warm_start=False",
            "anyOf": [
                {"type": "object", "properties": {"warm_start": {"enum": [False]}}},
                {"type": "object", "properties": {"oob_score": {"enum": [False]}}},
            ],
        },
    ],
}

_input_fit_schema = {
    "type": "object",
    "required": ["y", "X"],
    "properties": {
        "X": {
            "type": "array",
            "items": {
                "type": "array",
                "items": {"type": "number"},
            },
            "description": "The training input samples. Sparse matrices are accepted only if they are supported by the base estimator.",
        },
        "y": {
            "type": "array",
            "items": {"type": "number"},
            "description": "The target values (class labels in classification, real numbers in regression)",
        },
        "sample_weight": {
            "anyOf": [
                {
                    "type": "array",
                    "items": {"type": "number"},
                },
                {
                    "enum": [None],
                    "description": "Samples are equally weighted.",
                },
            ],
            "description": "Sample weights. Supported only if the base estimator supports sample weighting.",
        },
    },
}

_input_score_schema = {
    "description": "Return the coefficient of determination R^2 of the prediction.",
    "type": "object",
    "required": ["X", "y"],
    "properties": {
        "X": {
            "type": "array",
            "items": {
                "type": "array",
                "items": {"type": "number"},
            },
            "description": "Test samples. For some estimators this may be a precomputed kernel matrix or a list of generic objects instead with shape (n_samples, n_samples_fitted), where n_samples_fitted is the number of samples used in the fitting for the estimator.",
        },
        "y": {
            "type": "array",
            "items": {"type": "number"},
            "description": "True values for 'X'.",
        },
        "sample_weight": {
            "anyOf": [
                {
                    "type": "array",
                    "items": {"type": "number"},
                },
                {
                    "enum": [None],
                    "description": "Samples are equally weighted.",
                },
            ],
            "description": "Sample weights. Supported only if the base estimator supports sample weighting.",
        },
    },
}

_output_score_schema = {
    "description": "R^2 of 'self.predict' wrt 'y'",
    "type": "number",
}

_combined_schemas = {
    "$schema": "http://json-schema.org/draft-04/schema#",
    "description": """`Bagging classifier`_ from scikit-learn for bagging ensemble.

.. _`Bagging classifier`: https://scikit-learn.org/stable/modules/generated/sklearn.ensemble.BaggingClassifier.html
""",
    "documentation_url": "https://lale.readthedocs.io/en/latest/modules/lale.lib.sklearn.bagging_classifier.html",
    "import_from": "sklearn.ensemble",
    "type": "object",
    "tags": {"pre": [], "op": ["estimator", "regressor"], "post": []},
    "properties": {
        "hyperparams": _hyperparams_schema,
        "input_fit": _input_fit_schema,
        "input_predict": schema_X_numbers,
        "output_predict": schema_1D_numbers,
        "input_score": _input_score_schema,
        "output_score": _output_score_schema,
    },
}


BaggingRegressor = lale.operators.make_operator(
    _BaggingRegressorImpl, _combined_schemas
)

if lale.operators.sklearn_version >= version.Version("1.2"):
    BaggingRegressor = BaggingRegressor.customize_schema(
        base_estimator={
            "anyOf": [
                {"laleType": "operator"},
                {"enum": ["deprecated"]},
            ],
            "default": "deprecated",
            "description": "Deprecated. Use `estimator` instead.",
        },
        estimator={
            "anyOf": [
                {"laleType": "operator"},
                {"enum": [None], "description": "DecisionTreeClassifier"},
            ],
            "default": None,
            "description": "The base estimator to fit on random subsets of the dataset.",
        },
        constraint={
            "description": "Only `estimator` or `base_estimator` should be specified.  As `base_estimator` is deprecated, use `estimator`.",
            "anyOf": [
                {
                    "type": "object",
                    "properties": {"base_estimator": {"enum": [False, "deprecated"]}},
                },
                {
                    "type": "object",
                    "properties": {
                        "estimator": {"enum": [None]},
                    },
                },
            ],
        },
        set_as_available=True,
    )

lale.docstrings.set_docstrings(BaggingRegressor)
