from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal, localcontext
from enum import StrEnum

from nds_bot.domain.market.candle import Candle

CUBIC_DEGREE = 3
CUBIC_COEFFICIENT_COUNT = CUBIC_DEGREE + 1


class TrendNodeType(StrEnum):
    MAXIMUM = "MAX"
    MINIMUM = "MIN"
    STATIONARY_INFLECTION = "INFLECTION"


@dataclass(frozen=True, slots=True)
class TrendNode:
    """Stationary point of the fitted trend inside the fitted x-range."""

    x: Decimal
    time: datetime
    price: Decimal
    first_derivative: Decimal
    second_derivative: Decimal
    node_type: TrendNodeType


@dataclass(frozen=True, slots=True)
class CubicTrendFit:
    """Least-squares cubic fit over a candle-derived price series.

    x is the candle offset from the first supplied candle. The first candle uses
    x=0, the next x=1, and so on. The fitted function is:

        T(x) = a0 + a1*x + a2*x^2 + a3*x^3
    """

    coefficients: tuple[Decimal, Decimal, Decimal, Decimal]
    times: tuple[datetime, ...]
    midpoint_prices: tuple[Decimal, ...]
    fitted_prices: tuple[Decimal, ...]
    mse: Decimal

    @property
    def point_count(self) -> int:
        return len(self.times)

    @property
    def max_x(self) -> Decimal:
        return Decimal(self.point_count - 1)

    @property
    def a0(self) -> Decimal:
        return self.coefficients[0]

    @property
    def a1(self) -> Decimal:
        return self.coefficients[1]

    @property
    def a2(self) -> Decimal:
        return self.coefficients[2]

    @property
    def a3(self) -> Decimal:
        return self.coefficients[3]

    def evaluate(self, x: int | Decimal) -> Decimal:
        x_value = Decimal(x)
        return _evaluate_cubic(self.coefficients, x_value)

    def first_derivative(self, x: int | Decimal) -> Decimal:
        x_value = Decimal(x)
        return (
            self.a1
            + Decimal(2) * self.a2 * x_value
            + Decimal(3) * self.a3 * x_value * x_value
        )

    def second_derivative(self, x: int | Decimal) -> Decimal:
        x_value = Decimal(x)
        return Decimal(2) * self.a2 + Decimal(6) * self.a3 * x_value


def candle_midpoint(candle: Candle) -> Decimal:
    return (candle.high + candle.low) / Decimal(2)


def fit_cubic_midpoint_trend(candles: Sequence[Candle]) -> CubicTrendFit:
    """Fit a degree-3 polynomial to (High + Low) / 2 for each candle."""
    prices = tuple(candle_midpoint(candle) for candle in candles)
    return _fit_cubic_trend(candles, prices)


def fit_cubic_close_trend(candles: Sequence[Candle]) -> CubicTrendFit:
    """Fit a degree-3 polynomial to Close for each candle."""
    prices = tuple(candle.close for candle in candles)
    return _fit_cubic_trend(candles, prices)


def _fit_cubic_trend(
    candles: Sequence[Candle],
    prices: Sequence[Decimal],
) -> CubicTrendFit:
    if len(candles) < CUBIC_COEFFICIENT_COUNT:
        raise ValueError("at least 4 candles are required for a cubic fit")

    if len(prices) != len(candles):
        raise ValueError("trend prices must match candle count")

    first = candles[0]
    if any(
        candle.symbol != first.symbol or candle.timeframe is not first.timeframe
        for candle in candles
    ):
        raise ValueError("all trend candles must use the same symbol and timeframe")

    if any(
        current.opened_at >= following.opened_at
        for current, following in zip(candles, candles[1:], strict=False)
    ):
        raise ValueError("trend candles must be strictly chronological")

    observed_prices = tuple(prices)
    x_values = tuple(Decimal(index) for index in range(len(candles)))

    with localcontext() as context:
        context.prec = 50
        coefficients = _solve_cubic_normal_equations(x_values, observed_prices)
        fitted_prices = tuple(
            _evaluate_cubic(coefficients, x_value) for x_value in x_values
        )
        mse = sum(
            (observed - fitted) ** 2
            for observed, fitted in zip(
                observed_prices,
                fitted_prices,
                strict=True,
            )
        ) / Decimal(len(candles))

    return CubicTrendFit(
        coefficients=coefficients,
        times=tuple(candle.opened_at for candle in candles),
        midpoint_prices=observed_prices,
        fitted_prices=fitted_prices,
        mse=mse,
    )


def find_cubic_trend_nodes(trend_fit: CubicTrendFit) -> tuple[TrendNode, ...]:
    """Find stationary nodes from T'(x)=0 and classify them with T''(x)."""
    with localcontext() as context:
        context.prec = 50
        roots = _stationary_roots(trend_fit)
        nodes = [
            _build_trend_node(trend_fit, root)
            for root in roots
            if Decimal(0) <= root <= trend_fit.max_x
        ]

    return tuple(sorted(nodes, key=lambda node: node.x))


def _stationary_roots(trend_fit: CubicTrendFit) -> tuple[Decimal, ...]:
    quadratic = Decimal(3) * trend_fit.a3
    linear = Decimal(2) * trend_fit.a2
    constant = trend_fit.a1

    if quadratic == 0:
        if linear == 0:
            return ()
        return (-constant / linear,)

    discriminant = linear * linear - Decimal(4) * quadratic * constant
    if discriminant < 0:
        return ()

    denominator = Decimal(2) * quadratic
    square_root = discriminant.sqrt()
    first = (-linear - square_root) / denominator
    second = (-linear + square_root) / denominator

    if first == second:
        return (first,)
    return (first, second)


def _build_trend_node(trend_fit: CubicTrendFit, x_value: Decimal) -> TrendNode:
    first_derivative = trend_fit.first_derivative(x_value)
    second_derivative = trend_fit.second_derivative(x_value)

    if second_derivative > 0:
        node_type = TrendNodeType.MINIMUM
    elif second_derivative < 0:
        node_type = TrendNodeType.MAXIMUM
    else:
        node_type = TrendNodeType.STATIONARY_INFLECTION

    return TrendNode(
        x=x_value,
        time=_interpolate_trend_time(trend_fit.times, x_value),
        price=trend_fit.evaluate(x_value),
        first_derivative=first_derivative,
        second_derivative=second_derivative,
        node_type=node_type,
    )


def _interpolate_trend_time(
    times: Sequence[datetime],
    x_value: Decimal,
) -> datetime:
    if not times:
        raise ValueError("trend times cannot be empty")

    max_x = Decimal(len(times) - 1)
    if x_value < 0 or x_value > max_x:
        raise ValueError("node x is outside the trend time range")

    lower_index = int(x_value)
    if lower_index >= len(times) - 1:
        return times[-1]

    fraction = x_value - Decimal(lower_index)
    interval = times[lower_index + 1] - times[lower_index]
    interval_seconds = Decimal(str(interval.total_seconds()))
    offset_seconds = interval_seconds * fraction

    return times[lower_index] + timedelta(seconds=float(offset_seconds))


def _solve_cubic_normal_equations(
    x_values: Sequence[Decimal],
    y_values: Sequence[Decimal],
) -> tuple[Decimal, Decimal, Decimal, Decimal]:
    matrix = [
        [Decimal(0) for _ in range(CUBIC_COEFFICIENT_COUNT + 1)]
        for _ in range(CUBIC_COEFFICIENT_COUNT)
    ]

    for x_value, y_value in zip(x_values, y_values, strict=True):
        basis = _cubic_basis(x_value)

        for row_index in range(CUBIC_COEFFICIENT_COUNT):
            for column_index in range(CUBIC_COEFFICIENT_COUNT):
                matrix[row_index][column_index] += (
                    basis[row_index] * basis[column_index]
                )

            matrix[row_index][-1] += basis[row_index] * y_value

    solution = _gaussian_elimination(matrix)
    return (solution[0], solution[1], solution[2], solution[3])


def _cubic_basis(
    x_value: Decimal,
) -> tuple[Decimal, Decimal, Decimal, Decimal]:
    x_squared = x_value * x_value
    return (
        Decimal(1),
        x_value,
        x_squared,
        x_squared * x_value,
    )


def _gaussian_elimination(matrix: list[list[Decimal]]) -> list[Decimal]:
    size = CUBIC_COEFFICIENT_COUNT

    for pivot_column in range(size):
        pivot_row = max(
            range(pivot_column, size),
            key=lambda row_index: abs(matrix[row_index][pivot_column]),
        )
        if matrix[pivot_row][pivot_column] == 0:
            raise ValueError("cubic fit matrix is singular")

        if pivot_row != pivot_column:
            matrix[pivot_column], matrix[pivot_row] = (
                matrix[pivot_row],
                matrix[pivot_column],
            )

        pivot = matrix[pivot_column][pivot_column]
        matrix[pivot_column] = [
            value / pivot for value in matrix[pivot_column]
        ]

        for row_index in range(size):
            if row_index == pivot_column:
                continue

            factor = matrix[row_index][pivot_column]
            if factor == 0:
                continue

            matrix[row_index] = [
                current - factor * pivot_value
                for current, pivot_value in zip(
                    matrix[row_index],
                    matrix[pivot_column],
                    strict=True,
                )
            ]

    return [matrix[index][-1] for index in range(size)]


def _evaluate_cubic(
    coefficients: tuple[Decimal, Decimal, Decimal, Decimal],
    x_value: Decimal,
) -> Decimal:
    a0, a1, a2, a3 = coefficients
    return ((a3 * x_value + a2) * x_value + a1) * x_value + a0
