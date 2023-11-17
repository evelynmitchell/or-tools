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

"""Defines how to request a callback and the input and output of a callback."""
import dataclasses
import datetime
import enum
import math
from typing import Dict, List, Mapping, Optional, Set, Union

from ortools.math_opt import callback_pb2
from ortools.math_opt.python import model
from ortools.math_opt.python import sparse_containers


@enum.unique
class Event(enum.Enum):
    """The supported events during a solve for callbacks.

    * UNSPECIFIED: The event is unknown (typically an internal error).
    * PRESOLVE: The solver is currently running presolve. Gurobi only.
    * SIMPLEX: The solver is currently running the simplex method. Gurobi only.
    * MIP: The solver is in the MIP loop (called periodically before starting a
        new node). Useful for early termination. Note that this event does not
        provide information on LP relaxations nor about new incumbent solutions.
        Gurobi only.
    * MIP_SOLUTION: Called every time a new MIP incumbent is found. Fully
        supported by Gurobi, partially supported by CP-SAT (you can observe new
        solutions, but not add lazy constraints).
    * MIP_NODE: Called inside a MIP node. Note that there is no guarantee that the
        callback function will be called on every node. That behavior is
        solver-dependent. Gurobi only.

        Disabling cuts using SolveParameters may interfere with this event being
        called and/or adding cuts at this event, the behavior is solver specific.
    * BARRIER: Called in each iterate of an interior point/barrier method. Gurobi
        only.
    """

    UNSPECIFIED = callback_pb2.CALLBACK_EVENT_UNSPECIFIED
    PRESOLVE = callback_pb2.CALLBACK_EVENT_PRESOLVE
    SIMPLEX = callback_pb2.CALLBACK_EVENT_SIMPLEX
    MIP = callback_pb2.CALLBACK_EVENT_MIP
    MIP_SOLUTION = callback_pb2.CALLBACK_EVENT_MIP_SOLUTION
    MIP_NODE = callback_pb2.CALLBACK_EVENT_MIP_NODE
    BARRIER = callback_pb2.CALLBACK_EVENT_BARRIER


PresolveStats = callback_pb2.CallbackDataProto.PresolveStats
SimplexStats = callback_pb2.CallbackDataProto.SimplexStats
BarrierStats = callback_pb2.CallbackDataProto.BarrierStats
MipStats = callback_pb2.CallbackDataProto.MipStats


@dataclasses.dataclass
class CallbackData:
    """Input to the solve callback (produced by the solver).

    Attributes:
      event: The current state of the solver when the callback is run. The event
        (partially) determines what data is available and what the user is allowed
        to return.
      solution: A solution to the primal optimization problem, if available. For
        Event.MIP_SOLUTION, solution is always present, integral, and feasible.
        For Event.MIP_NODE, the primal_solution contains the current LP-node
        relaxation. In some cases, no solution will be available (e.g. because LP
        was infeasible or the solve was imprecise). Empty for other events.
      messages: Logs generated by the underlying solver, as a list of strings
        without new lines (each string is a line). Only filled on Event.MESSAGE.
      runtime: The time since Solve() was invoked.
      presolve_stats: Filled for Event.PRESOLVE only.
      simplex_stats: Filled for Event.SIMPLEX only.
      barrier_stats: Filled for Event.BARRIER only.
      mip_stats: Filled for the events MIP, MIP_SOLUTION and MIP_NODE only.
    """

    event: Event = Event.UNSPECIFIED
    solution: Optional[Dict[model.Variable, float]] = None
    messages: List[str] = dataclasses.field(default_factory=list)
    runtime: datetime.timedelta = datetime.timedelta()
    presolve_stats: PresolveStats = dataclasses.field(default_factory=PresolveStats)
    simplex_stats: SimplexStats = dataclasses.field(default_factory=SimplexStats)
    barrier_stats: BarrierStats = dataclasses.field(default_factory=BarrierStats)
    mip_stats: MipStats = dataclasses.field(default_factory=MipStats)


def parse_callback_data(
    cb_data: callback_pb2.CallbackDataProto, mod: model.Model
) -> CallbackData:
    """Creates a CallbackData from an equivalent proto.

    Args:
      cb_data: A protocol buffer with the information the user needs for a
        callback.
      mod: The model being solved.

    Returns:
      An equivalent CallbackData.

    Raises:
      ValueError: if cb_data is invalid or inconsistent with mod, e.g. cb_data
      refers to a variable id not in mod.
    """
    result = CallbackData()
    result.event = Event(cb_data.event)
    if cb_data.HasField("primal_solution_vector"):
        primal_solution = cb_data.primal_solution_vector
        result.solution = {
            mod.get_variable(id): val
            for (id, val) in zip(primal_solution.ids, primal_solution.values)
        }
    result.runtime = cb_data.runtime.ToTimedelta()
    result.presolve_stats = cb_data.presolve_stats
    result.simplex_stats = cb_data.simplex_stats
    result.barrier_stats = cb_data.barrier_stats
    result.mip_stats = cb_data.mip_stats
    return result


@dataclasses.dataclass
class CallbackRegistration:
    """Request the events and input data and reports output types for a callback.

    Note that it is an error to add a constraint in a callback without setting
    add_cuts and/or add_lazy_constraints to true.

    Attributes:
      events: When the callback should be invoked, by default, never. If an
        unsupported event for a solver/model combination is selected, an
        excecption is raised, see Event above for details.
      mip_solution_filter: restricts the variable values returned in
        CallbackData.solution (the callback argument) at each MIP_SOLUTION event.
        By default, values are returned for all variables.
      mip_node_filter: restricts the variable values returned in
        CallbackData.solution (the callback argument) at each MIP_NODE event. By
        default, values are returned for all variables.
      add_cuts: The callback may add "user cuts" (linear constraints that
        strengthen the LP without cutting of integer points) at MIP_NODE events.
      add_lazy_constraints: The callback may add "lazy constraints" (linear
        constraints that cut off integer solutions) at MIP_NODE or MIP_SOLUTION
        events.
    """

    events: Set[Event] = dataclasses.field(default_factory=set)
    mip_solution_filter: sparse_containers.VariableFilter = (
        sparse_containers.VariableFilter()
    )
    mip_node_filter: sparse_containers.VariableFilter = (
        sparse_containers.VariableFilter()
    )
    add_cuts: bool = False
    add_lazy_constraints: bool = False

    def to_proto(self) -> callback_pb2.CallbackRegistrationProto:
        """Returns an equivalent proto to this CallbackRegistration."""
        result = callback_pb2.CallbackRegistrationProto()
        result.request_registration[:] = sorted([event.value for event in self.events])
        result.mip_solution_filter.CopyFrom(self.mip_solution_filter.to_proto())
        result.mip_node_filter.CopyFrom(self.mip_node_filter.to_proto())
        result.add_cuts = self.add_cuts
        result.add_lazy_constraints = self.add_lazy_constraints
        return result


@dataclasses.dataclass
class GeneratedConstraint:
    """A linear constraint to add inside a callback.

    Models a constraint of the form:
      lb <= sum_{i in I} a_i * x_i <= ub

    Two types of generated linear constraints are supported based on is_lazy:
      * The "lazy constraint" can remove integer points from the feasible
        region and can be added at event Event.MIP_NODE or
        Event.MIP_SOLUTION
      * The "user cut" (on is_lazy=false) strengthens the LP without removing
        integer points. It can only be added at Event.MIP_NODE.


    Attributes:
      terms: The variables and linear coefficients in the constraint, a_i and x_i
        in the model above.
      lower_bound: lb in the model above.
      upper_bound: ub in the model above.
      is_lazy: Indicates if the constraint should be interpreted as a "lazy
        constraint" (cuts off integer solutions) or a "user cut" (strengthens the
        LP relaxation without cutting of integer solutions).
    """

    terms: Mapping[model.Variable, float] = dataclasses.field(default_factory=dict)
    lower_bound: float = -math.inf
    upper_bound: float = math.inf
    is_lazy: bool = False

    def to_proto(
        self,
    ) -> callback_pb2.CallbackResultProto.GeneratedLinearConstraint:
        """Returns an equivalent proto for the constraint."""
        result = callback_pb2.CallbackResultProto.GeneratedLinearConstraint()
        result.is_lazy = self.is_lazy
        result.lower_bound = self.lower_bound
        result.upper_bound = self.upper_bound
        result.linear_expression.CopyFrom(
            sparse_containers.to_sparse_double_vector_proto(self.terms)
        )
        return result


@dataclasses.dataclass
class CallbackResult:
    """The value returned by a solve callback (produced by the user).

    Attributes:
      terminate: Stop the solve process and return early. Can be called from any
        event.
      generated_constraints: Constraints to add to the model. For details, see
        GeneratedConstraint documentation.
      suggested_solutions: A list of solutions (or partially defined solutions) to
        suggest to the solver. Some solvers (e.g. gurobi) will try and convert a
        partial solution into a full solution by solving a MIP. Use only for
        Event.MIP_NODE.
    """

    terminate: bool = False
    generated_constraints: List[GeneratedConstraint] = dataclasses.field(
        default_factory=list
    )
    suggested_solutions: List[Mapping[model.Variable, float]] = dataclasses.field(
        default_factory=list
    )

    def add_generated_constraint(
        self,
        bounded_expr: Optional[Union[bool, model.BoundedLinearTypes]] = None,
        *,
        lb: Optional[float] = None,
        ub: Optional[float] = None,
        expr: Optional[model.LinearTypes] = None,
        is_lazy: bool,
    ) -> None:
        """Adds a linear constraint to the list of generated constraints.

        The constraint can be of two exclusive types: a "lazy constraint" or a
        "user cut. A "user cut" is a constraint that excludes the current LP
        solution, but does not cut off any integer-feasible points that satisfy the
        already added constraints (either in callbacks or through
        Model.add_linear_constraint()). A "lazy constraint" is a constraint that
        excludes such integer-feasible points and hence is needed for corrctness of
        the forlumation.

        The simplest way to specify the constraint is by passing a one-sided or
        two-sided linear inequality as in:
          * add_generated_constraint(x + y + 1.0 <= 2.0, is_lazy=True),
          * add_generated_constraint(x + y >= 2.0, is_lazy=True), or
          * add_generated_constraint((1.0 <= x + y) <= 2.0, is_lazy=True).

        Note the extra parenthesis for two-sided linear inequalities, which is
        required due to some language limitations (see
        https://peps.python.org/pep-0335/ and https://peps.python.org/pep-0535/).
        If the parenthesis are omitted, a TypeError will be raised explaining the
        issue (if this error was not raised the first inequality would have been
        silently ignored because of the noted language limitations).

        The second way to specify the constraint is by setting lb, ub, and/o expr as
        in:
          * add_generated_constraint(expr=x + y + 1.0, ub=2.0, is_lazy=True),
          * add_generated_constraint(expr=x + y, lb=2.0, is_lazy=True),
          * add_generated_constraint(expr=x + y, lb=1.0, ub=2.0, is_lazy=True), or
          * add_generated_constraint(lb=1.0, is_lazy=True).
        Omitting lb is equivalent to setting it to -math.inf and omiting ub is
        equivalent to setting it to math.inf.

        These two alternatives are exclusive and a combined call like:
          * add_generated_constraint(x + y <= 2.0, lb=1.0, is_lazy=True), or
          * add_generated_constraint(x + y <= 2.0, ub=math.inf, is_lazy=True)
        will raise a ValueError. A ValueError is also raised if expr's offset is
        infinite.

        Args:
          bounded_expr: a linear inequality describing the constraint. Cannot be
            specified together with lb, ub, or expr.
          lb: The constraint's lower bound if bounded_expr is omitted (if both
            bounder_expr and lb are omitted, the lower bound is -math.inf).
          ub: The constraint's upper bound if bounded_expr is omitted (if both
            bounder_expr and ub are omitted, the upper bound is math.inf).
          expr: The constraint's linear expression if bounded_expr is omitted.
          is_lazy: Whether the constraint is lazy or not.
        """
        normalized_inequality = model.as_normalized_linear_inequality(
            bounded_expr, lb=lb, ub=ub, expr=expr
        )
        self.generated_constraints.append(
            GeneratedConstraint(
                lower_bound=normalized_inequality.lb,
                terms=normalized_inequality.coefficients,
                upper_bound=normalized_inequality.ub,
                is_lazy=is_lazy,
            )
        )

    def add_lazy_constraint(
        self,
        bounded_expr: Optional[Union[bool, model.BoundedLinearTypes]] = None,
        *,
        lb: Optional[float] = None,
        ub: Optional[float] = None,
        expr: Optional[model.LinearTypes] = None,
    ) -> None:
        """Shortcut for add_generated_constraint(..., is_lazy=True).."""
        self.add_generated_constraint(
            bounded_expr, lb=lb, ub=ub, expr=expr, is_lazy=True
        )

    def add_user_cut(
        self,
        bounded_expr: Optional[Union[bool, model.BoundedLinearTypes]] = None,
        *,
        lb: Optional[float] = None,
        ub: Optional[float] = None,
        expr: Optional[model.LinearTypes] = None,
    ) -> None:
        """Shortcut for add_generated_constraint(..., is_lazy=False)."""
        self.add_generated_constraint(
            bounded_expr, lb=lb, ub=ub, expr=expr, is_lazy=False
        )

    def to_proto(self) -> callback_pb2.CallbackResultProto:
        """Returns a proto equivalent to this CallbackResult."""
        result = callback_pb2.CallbackResultProto(terminate=self.terminate)
        for generated_constraint in self.generated_constraints:
            result.cuts.add().CopyFrom(generated_constraint.to_proto())
        for suggested_solution in self.suggested_solutions:
            result.suggested_solutions.add().CopyFrom(
                sparse_containers.to_sparse_double_vector_proto(suggested_solution)
            )
        return result
