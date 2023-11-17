#!/usr/bin/env python3
# Copyright 2010-2022 Google LLC
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Solve a linear regression problem on random data.

Problem data:
  There are num_features features, indexed by j.
  There are num_examples training examples indexed by i.
  x_ij: The feature value for example i and feature j in the training data.
  y_i: The label for example i in the training data.

Decision variables:
  beta_j: the coefficient to learn for each feature j.
  z_i: the prediction error for example i.

Optimization problem:
   min   sum_i z_i^2
   s.t.  y_i - sum_j beta_j * x_ij = z_i

This is the unregularized linear regression problem.

This example solves the problem on randomly generated (x, y) data. The data
is generated by assuming some true values for beta (generated at random,
i.i.d. N(0, 1)), then drawing each x_ij as N(0, 1) and then computing
  y_i = beta * x_i + N(0, noise)
where noise is a command line flag.

After solving the optimization problem above to recover values for beta, the
in sample and out of sample loss (average squared prediction error) for the
learned model are printed.

For an advanced version, see:
  ortools/math_opt/codelabs/regression/
"""
import dataclasses
from typing import Sequence

from absl import app
from absl import flags
import numpy as np

from ortools.math_opt.python import mathopt

_SOLVER_TYPE = flags.DEFINE_enum_class(
    "solver_type",
    mathopt.SolverType.PDLP,
    mathopt.SolverType,
    "The solver needs to support quadratic objectives, e.g. pdlp, gurobi, or " "osqp.",
)

_NUM_FEATURES = flags.DEFINE_integer(
    "num_features", 10, "The number of features in the linear regression model."
)

_NUM_EXAMPLES = flags.DEFINE_integer(
    "num_examples",
    100,
    "The number of examples to use in the train and test sets.",
)

_NOISE = flags.DEFINE_float(
    "noise", 3.0, "The standard deviation of the noise on the labels."
)


@dataclasses.dataclass
class LabeledData:
    xs: np.ndarray
    ys: np.ndarray


def random_data(
    betas: np.ndarray,
    num_examples: int,
    noise_stddev: float,
    rng: np.random._generator.Generator,
) -> LabeledData:
    """Creates randomly perturbed labeled data from a ground truth beta."""
    num_features = betas.shape[0]
    xs = rng.standard_normal(size=(num_examples, num_features))
    ys = xs @ betas + rng.normal(0, noise_stddev, size=(num_examples))
    return LabeledData(xs=xs, ys=ys)


def l2_loss(betas: np.ndarray, labeled_data: LabeledData) -> float:
    """Computes the average squared error between model(labeled_data.xs) and labeled_data.y."""
    num_examples = labeled_data.xs.shape[0]
    if num_examples == 0:
        return 0
    residuals = labeled_data.xs @ betas - labeled_data.ys
    return np.inner(residuals, residuals) / num_examples


def train(labeled_data: LabeledData, solver_type: mathopt.SolverType) -> np.ndarray:
    """Returns minimum L2Loss beta on labeled_data by solving a quadratic optimization problem."""
    num_examples, num_features = labeled_data.xs.shape

    model = mathopt.Model(name="linear_regression")

    # Create the decision variables: beta, and z.
    betas = [model.add_variable(name=f"beta_{j}") for j in range(num_features)]
    zs = [model.add_variable(name=f"z_{i}") for i in range(num_examples)]

    # Set the objective function:
    model.minimize(sum(z * z for z in zs))

    # Add the constraints:
    #      z_i = y_i - x_i * beta
    for i in range(num_examples):
        model.add_linear_constraint(
            zs[i]
            == labeled_data.ys[i]
            - sum(betas[j] * labeled_data.xs[i, j] for j in range(num_features))
        )

    # Done building the model, now solve.
    result = mathopt.solve(
        model, solver_type, params=mathopt.SolveParameters(enable_output=True)
    )
    if result.termination.reason != mathopt.TerminationReason.OPTIMAL:
        raise RuntimeError(
            "Expected termination reason optimal, but termination was: "
            f"{result.termination}"
        )
    print(f"Training time: {result.solve_time()}")
    return np.array(result.variable_values(betas))


def main(argv: Sequence[str]) -> None:
    del argv  # Unused.

    num_features = _NUM_FEATURES.value
    num_examples = _NUM_EXAMPLES.value
    noise_stddev = _NOISE.value

    rng = np.random.default_rng(123)

    ground_truth_betas = rng.standard_normal(size=(num_features))
    train_data = random_data(ground_truth_betas, num_examples, noise_stddev, rng)
    test_data = random_data(ground_truth_betas, num_examples, noise_stddev, rng)

    learned_beta = train(train_data, _SOLVER_TYPE.value)
    print(f"In sample loss: {l2_loss(learned_beta, train_data)}")
    print(f"Out of sample loss: {l2_loss(learned_beta, test_data)}")


if __name__ == "__main__":
    app.run(main)
