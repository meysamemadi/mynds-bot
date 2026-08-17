from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, localcontext

from nds_bot.domain.market.candle import Candle

CUBIC_DEGREE = 3
CUBIC_COEFFICIENT_COUNT = CUBIC_DEGREE + 1


@dataclass(frozen=True, slots=True)
class CubicTrendFit:
    """Least-squares cubic fit over candle midpoint prices.

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


def candle_midpoint(candle: Candle) -> Decimal:
    return (candle.high + candle.low) / Decimal(2)


def fit_cubic_midpoint_trend(candles: Sequence[Candle]) -> CubicTrendFit:
    """Fit a degree-3 polynomial to (High + Low) / 2 for each candle."""
    if len(candles) < CUBIC_COEFFICIENT_COUNT:
        raise ValueError("at least 4 candles are required for a cubic fit")

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

    midpoint_prices = tuple(candle_midpoint(candle) for candle in candles)
    x_values = tuple(Decimal(index) for index in range(len(candles)))

    with localcontext() as context:
        context.prec = 50
        coefficients = _solve_cubic_normal_equations(x_values, midpoint_prices)
        fitted_prices = tuple(
            _evaluate_cubic(coefficients, x_value) for x_value in x_values
        )
        mse = sum(
            (observed - fitted) ** 2
            for observed, fitted in zip(
                midpoint_prices,
                fitted_prices,
                strict=True,
            )
        ) / Decimal(len(candles))

    return CubicTrendFit(
        coefficients=coefficients,
        times=tuple(candle.opened_at for candle in candles),
        midpoint_prices=midpoint_prices,
        fitted_prices=fitted_prices,
        mse=mse,
    )


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
