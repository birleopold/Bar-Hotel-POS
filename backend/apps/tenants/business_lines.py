from __future__ import annotations

from dataclasses import dataclass

from apps.tenants.models import OutletType


DEFAULT_MODULES_ALL: list[str] = [
    "pos",
    "kitchen",
    "promotions",
    "inventory",
    "purchasing",
    "lodging",
    "events",
    "finance",
    "workspace",
]

CORE_POS_MODULES = ["pos", "promotions", "inventory", "purchasing", "finance", "workspace"]
BAR_MODULES = [*CORE_POS_MODULES, "kitchen"]
FOOD_MODULES = [*CORE_POS_MODULES, "kitchen"]
LODGING_MODULES = ["lodging", "finance", "workspace"]
EVENT_MODULES = ["events", "finance", "workspace"]


@dataclass(frozen=True, slots=True)
class BusinessLineProfile:
    key: str
    label: str
    default_outlet_type: str
    default_outlet_name: str
    default_modules: list[str]


BUSINESS_LINES: dict[str, BusinessLineProfile] = {
    "bar": BusinessLineProfile(
        key="bar",
        label="Bar",
        default_outlet_type=OutletType.BAR,
        default_outlet_name="Main bar",
        default_modules=BAR_MODULES,
    ),
    "lounge": BusinessLineProfile(
        key="lounge",
        label="Lounge",
        default_outlet_type=OutletType.LOUNGE,
        default_outlet_name="Main lounge",
        default_modules=BAR_MODULES,
    ),
    "restaurant": BusinessLineProfile(
        key="restaurant",
        label="Restaurant",
        default_outlet_type=OutletType.RESTAURANT,
        default_outlet_name="Main restaurant",
        default_modules=FOOD_MODULES,
    ),
    "cafeteria": BusinessLineProfile(
        key="cafeteria",
        label="Cafeteria",
        default_outlet_type=OutletType.CAFETERIA,
        default_outlet_name="Main cafeteria",
        default_modules=FOOD_MODULES,
    ),
    "kitchen": BusinessLineProfile(
        key="kitchen",
        label="Kitchen / food preparation",
        default_outlet_type=OutletType.RESTAURANT,
        default_outlet_name="Kitchen",
        default_modules=["kitchen", "inventory", "purchasing", "workspace"],
    ),
    "lodging": BusinessLineProfile(
        key="lodging",
        label="Lodging",
        default_outlet_type=OutletType.LODGING_FRONT_DESK,
        default_outlet_name="Front desk",
        default_modules=LODGING_MODULES,
    ),
    "retail": BusinessLineProfile(
        key="retail",
        label="Retail / shop",
        default_outlet_type=OutletType.RETAIL,
        default_outlet_name="Main shop",
        default_modules=CORE_POS_MODULES,
    ),
    "supermarket": BusinessLineProfile(
        key="supermarket",
        label="Supermarket / grocery",
        default_outlet_type=OutletType.SUPERMARKET,
        default_outlet_name="Main supermarket",
        default_modules=CORE_POS_MODULES,
    ),
    "events": BusinessLineProfile(
        key="events",
        label="Events / event space",
        default_outlet_type=OutletType.EVENT_SPACE,
        default_outlet_name="Main event space",
        default_modules=EVENT_MODULES,
    ),
    "services": BusinessLineProfile(
        key="services",
        label="Services / spa / appointments",
        default_outlet_type=OutletType.SERVICE,
        default_outlet_name="Services desk",
        default_modules=["pos", "finance", "workspace"],
    ),
}


def normalize_business_lines(values: list[str] | None) -> list[str]:
    raw = values or []
    out: list[str] = []
    seen: set[str] = set()
    for v in raw:
        key = str(v or "").strip().lower()
        if not key:
            continue
        if key not in BUSINESS_LINES:
            continue
        if key in seen:
            continue
        seen.add(key)
        out.append(key)
    return out


def modules_for_business_lines(lines: list[str]) -> list[str]:
    modules: list[str] = []
    seen: set[str] = set()
    for key in lines:
        p = BUSINESS_LINES.get(key)
        if not p:
            continue
        for m in p.default_modules:
            if m not in seen:
                seen.add(m)
                modules.append(m)
    return modules


def outlet_types_for_business_lines(lines: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for key in lines:
        p = BUSINESS_LINES.get(key)
        if not p:
            continue
        if p.default_outlet_type not in seen:
            seen.add(p.default_outlet_type)
            out.append(p.default_outlet_type)
    return out
