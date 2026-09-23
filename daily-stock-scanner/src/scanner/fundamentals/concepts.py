"""Concepts comptables canoniques et correspondance avec les taxonomies des fournisseurs.

Chaque concept a une nature :

* ``flow``  : grandeur de flux sur une période (chiffre d'affaires, EBIT, CFO…)
* ``stock`` : grandeur de bilan à une date (actif total, dette…)
* ``per_share`` : grandeur par action sur une période (BPA)

Les listes de tags sont ordonnées par priorité : pour une même période, le premier tag
disponible l'emporte (les sociétés n'utilisent pas toutes les mêmes tags US-GAAP).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Nature = Literal["flow", "stock", "per_share"]


@dataclass(frozen=True)
class Concept:
    name: str
    nature: Nature
    us_gaap: tuple[str, ...] = ()
    eodhd: tuple[str, ...] = ()  # champs EODHD (Financials::*)
    absolute: bool = False  # valeur rendue positive (ex. capex, décaissement)


CONCEPTS: dict[str, Concept] = {
    c.name: c
    for c in (
        # ------------------------------------------------------------------ compte de résultat
        Concept(
            "revenue",
            "flow",
            (
                "Revenues",
                "RevenueFromContractWithCustomerExcludingAssessedTax",
                "SalesRevenueNet",
                "RevenueFromContractWithCustomerIncludingAssessedTax",
                "SalesRevenueGoodsNet",
            ),
            ("totalRevenue",),
        ),
        Concept(
            "cogs",
            "flow",
            ("CostOfRevenue", "CostOfGoodsAndServicesSold", "CostOfGoodsSold", "CostOfServices"),
            ("costOfRevenue",),
        ),
        Concept("gross_profit", "flow", ("GrossProfit",), ("grossProfit",)),
        Concept(
            "sga",
            "flow",
            ("SellingGeneralAndAdministrativeExpense",),
            ("sellingGeneralAdministrative",),
        ),
        Concept("ebit", "flow", ("OperatingIncomeLoss",), ("operatingIncome", "ebit")),
        Concept(
            "pretax_income",
            "flow",
            (
                "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
                "IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments",
            ),
            ("incomeBeforeTax",),
        ),
        Concept("income_tax", "flow", ("IncomeTaxExpenseBenefit",), ("incomeTaxExpense",)),
        Concept(
            "net_income",
            "flow",
            ("NetIncomeLoss", "ProfitLoss", "NetIncomeLossAvailableToCommonStockholdersBasic"),
            ("netIncome",),
        ),
        Concept(
            "interest_expense",
            "flow",
            ("InterestExpense", "InterestExpenseNonoperating", "InterestExpenseDebt"),
            ("interestExpense",),
            absolute=True,
        ),
        Concept(
            "depreciation",
            "flow",
            (
                "DepreciationDepletionAndAmortization",
                "DepreciationAndAmortization",
                "Depreciation",
                "DepreciationAmortizationAndAccretionNet",
            ),
            ("depreciationAndAmortization", "depreciation"),
            absolute=True,
        ),
        Concept(
            "eps_diluted",
            "per_share",
            ("EarningsPerShareDiluted", "EarningsPerShareBasicAndDiluted", "EarningsPerShareBasic"),
            (),
        ),
        # --------------------------------------------------------------------- flux de trésorerie
        Concept(
            "cfo",
            "flow",
            (
                "NetCashProvidedByUsedInOperatingActivities",
                "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations",
            ),
            ("totalCashFromOperatingActivities",),
        ),
        Concept(
            "capex",
            "flow",
            ("PaymentsToAcquirePropertyPlantAndEquipment", "PaymentsToAcquireProductiveAssets"),
            ("capitalExpenditures",),
            absolute=True,
        ),
        # ------------------------------------------------------------------------------ bilan
        Concept("total_assets", "stock", ("Assets",), ("totalAssets",)),
        Concept("current_assets", "stock", ("AssetsCurrent",), ("totalCurrentAssets",)),
        Concept(
            "current_liabilities", "stock", ("LiabilitiesCurrent",), ("totalCurrentLiabilities",)
        ),
        Concept("total_liabilities", "stock", ("Liabilities",), ("totalLiab",)),
        Concept("liabilities_and_equity", "stock", ("LiabilitiesAndStockholdersEquity",), ()),
        Concept(
            "total_equity",
            "stock",
            (
                "StockholdersEquity",
                "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
            ),
            ("totalStockholderEquity",),
        ),
        Concept(
            "cash",
            "stock",
            (
                "CashAndCashEquivalentsAtCarryingValue",
                "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
                "Cash",
            ),
            ("cash", "cashAndEquivalents"),
        ),
        Concept(
            "receivables",
            "stock",
            ("AccountsReceivableNetCurrent", "ReceivablesNetCurrent"),
            ("netReceivables",),
        ),
        Concept("inventory", "stock", ("InventoryNet",), ("inventory",)),
        Concept(
            "ppe_net",
            "stock",
            ("PropertyPlantAndEquipmentNet",),
            ("propertyPlantAndEquipmentNet", "propertyPlantEquipment"),
        ),
        Concept(
            "long_term_debt",
            "stock",
            ("LongTermDebtNoncurrent", "LongTermDebt", "LongTermDebtAndCapitalLeaseObligations"),
            ("longTermDebt",),
        ),
        Concept(
            "short_term_debt",
            "stock",
            ("LongTermDebtCurrent", "DebtCurrent", "ShortTermBorrowings"),
            ("shortTermDebt", "shortLongTermDebt"),
        ),
        Concept(
            "retained_earnings",
            "stock",
            ("RetainedEarningsAccumulatedDeficit",),
            ("retainedEarnings",),
        ),
        Concept(
            "shares_outstanding",
            "stock",
            ("dei:EntityCommonStockSharesOutstanding", "CommonStockSharesOutstanding"),
            ("commonStockSharesOutstanding",),
        ),
    )
}


# Taxonomie ifrs-full : émetteurs étrangers déposant un 20-F IFRS sur EDGAR, et rapports
# ESEF européens (Phase 2). Même logique de priorité que pour US-GAAP.
IFRS_TAGS: dict[str, tuple[str, ...]] = {
    "revenue": ("Revenue", "RevenueFromContractsWithCustomers"),
    "cogs": ("CostOfSales",),
    "gross_profit": ("GrossProfit",),
    "sga": ("SellingGeneralAndAdministrativeExpense",),
    "ebit": ("ProfitLossFromOperatingActivities",),
    "pretax_income": ("ProfitLossBeforeTax",),
    "income_tax": ("IncomeTaxExpenseContinuingOperations",),
    "net_income": ("ProfitLossAttributableToOwnersOfParent", "ProfitLoss"),
    "interest_expense": ("FinanceCosts", "InterestExpense"),
    "depreciation": ("DepreciationAndAmortisationExpense", "DepreciationPropertyPlantAndEquipment"),
    "eps_diluted": ("DilutedEarningsLossPerShare", "BasicEarningsLossPerShare"),
    "cfo": ("CashFlowsFromUsedInOperatingActivities",),
    "capex": (
        "PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities",
        "PurchaseOfPropertyPlantAndEquipment",
    ),
    "total_assets": ("Assets",),
    "current_assets": ("CurrentAssets",),
    "current_liabilities": ("CurrentLiabilities",),
    "total_liabilities": ("Liabilities",),
    "liabilities_and_equity": ("EquityAndLiabilities",),
    "total_equity": ("EquityAttributableToOwnersOfParent", "Equity"),
    "cash": ("CashAndCashEquivalents",),
    "receivables": ("TradeAndOtherCurrentReceivables", "CurrentTradeReceivables"),
    "inventory": ("Inventories",),
    "ppe_net": ("PropertyPlantAndEquipment",),
    "long_term_debt": ("LongtermBorrowings", "NoncurrentPortionOfLongtermBorrowings"),
    "short_term_debt": ("ShorttermBorrowings", "CurrentPortionOfLongtermBorrowings"),
    "retained_earnings": ("RetainedEarnings",),
    "shares_outstanding": ("NumberOfSharesOutstanding",),
}


def us_gaap_index() -> dict[str, tuple[str, int]]:
    """tag US-GAAP (ou ``dei:...``) -> (concept canonique, rang de priorité)."""
    out: dict[str, tuple[str, int]] = {}
    for concept in CONCEPTS.values():
        for rank, tag in enumerate(concept.us_gaap):
            out.setdefault(tag, (concept.name, rank))
    return out


def ifrs_index() -> dict[str, tuple[str, int]]:
    out: dict[str, tuple[str, int]] = {}
    for name, tags in IFRS_TAGS.items():
        for rank, tag in enumerate(tags):
            out.setdefault(tag, (name, rank))
    return out


def eodhd_index() -> dict[str, tuple[str, int]]:
    out: dict[str, tuple[str, int]] = {}
    for concept in CONCEPTS.values():
        for rank, field in enumerate(concept.eodhd):
            out.setdefault(field, (concept.name, rank))
    return out
