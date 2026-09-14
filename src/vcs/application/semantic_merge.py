from __future__ import annotations

import copy
from typing import Any, Dict, List, Tuple

from src.vcs.domain.merge import FieldConflict


class SemanticMergeEngine:
    @classmethod
    def merge(
            cls,
            base: Dict[str, Any],
            ours: Dict[str, Any],
            theirs: Dict[str, Any],
    ) -> Tuple[Dict[str, Any], List[FieldConflict]]:
        merged: Dict[str, Any] = {}
        conflicts: List[FieldConflict] = []

        # Merge top-level scalar / optional fields (e.g. dynamic_quantity)
        all_top_keys = set(base.keys()) | set(ours.keys()) | set(theirs.keys())
        all_top_keys.discard("assets")

        for key in sorted(all_top_keys):
            base_val = base.get(key)
            ours_val = ours.get(key)
            theirs_val = theirs.get(key)

            if ours_val == theirs_val:
                merged[key] = ours_val
            elif base_val == ours_val:
                merged[key] = theirs_val
            elif base_val == theirs_val:
                merged[key] = ours_val
            else:
                conflicts.append(
                    FieldConflict(
                        path=key,
                        base_value=base_val,
                        ours_value=ours_val,
                        theirs_value=theirs_val,
                        description=f"Conflicting values for top-level '{key}'",
                    )
                )
                merged[key] = ours_val  # Default to ours pending resolution

        # Merge assets collection
        merged_assets, asset_conflicts = cls._merge_assets(
            base.get("assets", []),
            ours.get("assets", []),
            theirs.get("assets", []),
        )
        merged["assets"] = merged_assets
        conflicts.extend(asset_conflicts)

        return merged, conflicts

    @classmethod
    def _asset_key(cls, asset: Dict[str, Any]) -> str:
        base = str(asset.get("base_ticker_symbol", "")).upper()
        quote = str(asset.get("quote_ticker_symbol", "")).upper()
        name = str(asset.get("name", ""))
        return f"{base}_{quote}" if (base and quote) else name

    @classmethod
    def _merge_assets(
        cls,
        base_assets: List[Dict[str, Any]],
        ours_assets: List[Dict[str, Any]],
        theirs_assets: List[Dict[str, Any]],
    ) -> Tuple[List[Dict[str, Any]], List[FieldConflict]]:
        base_map = {cls._asset_key(a): copy.deepcopy(a) for a in base_assets}
        ours_map = {cls._asset_key(a): copy.deepcopy(a) for a in ours_assets}
        theirs_map = {cls._asset_key(a): copy.deepcopy(a) for a in theirs_assets}

        all_keys = list(dict.fromkeys(list(ours_map.keys()) + list(theirs_map.keys()) + list(base_map.keys())))
        merged_assets: List[Dict[str, Any]] = []
        conflicts: List[FieldConflict] = []

        for key in all_keys:
            in_base = key in base_map
            in_ours = key in ours_map
            in_theirs = key in theirs_map

            if not in_base:
                if in_ours and in_theirs:
                    merged_asset, a_conflicts = cls._merge_single_asset(
                        key, {}, ours_map[key], theirs_map[key]
                    )
                    merged_assets.append(merged_asset)
                    conflicts.extend(a_conflicts)
                elif in_ours:
                    merged_assets.append(ours_map[key])
                elif in_theirs:
                    merged_assets.append(theirs_map[key])
                continue

            base_asset = base_map[key]

            if in_ours and in_theirs:
                merged_asset, a_conflicts = cls._merge_single_asset(
                    key, base_asset, ours_map[key], theirs_map[key]
                )
                merged_assets.append(merged_asset)
                conflicts.extend(a_conflicts)
            elif in_ours and not in_theirs:
                if ours_map[key] == base_asset:
                    # theirs deleted unchanged asset -> delete
                    pass
                else:
                    conflicts.append(
                        FieldConflict(
                            path=f"assets.{key}",
                            base_value="Present",
                            ours_value="Modified",
                            theirs_value="Deleted",
                            description=f"Asset '{key}' modified on main but deleted on backtest branch",
                        )
                    )
                    merged_assets.append(ours_map[key])
            elif not in_ours and in_theirs:
                if theirs_map[key] == base_asset:
                    # ours deleted unchanged asset -> delete
                    pass
                else:
                    conflicts.append(
                        FieldConflict(
                            path=f"assets.{key}",
                            base_value="Present",
                            ours_value="Deleted",
                            theirs_value="Modified",
                            description=f"Asset '{key}' deleted on main but modified on backtest branch",
                        )
                    )
                    merged_assets.append(theirs_map[key])

        return merged_assets, conflicts

    @classmethod
    def _merge_single_asset(
        cls,
        asset_key: str,
        base: Dict[str, Any],
        ours: Dict[str, Any],
        theirs: Dict[str, Any],
    ) -> Tuple[Dict[str, Any], List[FieldConflict]]:
        merged: Dict[str, Any] = {}
        conflicts: List[FieldConflict] = []

        all_fields = set(base.keys()) | set(ours.keys()) | set(theirs.keys())

        for field in sorted(all_fields):
            base_f = base.get(field)
            ours_f = ours.get(field)
            theirs_f = theirs.get(field)

            if field == "strategies":
                merged_strats, strat_conflicts = cls._merge_strategies(
                    asset_key,
                    base_f or [],
                    ours_f or [],
                    theirs_f or [],
                )
                merged[field] = merged_strats
                conflicts.extend(strat_conflicts)
            elif field in ("consensus", "guard_config") and (
                isinstance(ours_f, dict) or isinstance(theirs_f, dict) or isinstance(base_f, dict)
            ):
                merged_sub, sub_conflicts = cls._merge_subdict(
                    f"assets.{asset_key}.{field}",
                    base_f or {},
                    ours_f or {},
                    theirs_f or {},
                )
                merged[field] = merged_sub
                conflicts.extend(sub_conflicts)
            else:
                if ours_f == theirs_f:
                    merged[field] = ours_f
                elif base_f == ours_f:
                    merged[field] = theirs_f
                elif base_f == theirs_f:
                    merged[field] = ours_f
                else:
                    conflicts.append(
                        FieldConflict(
                            path=f"assets.{asset_key}.{field}",
                            base_value=base_f,
                            ours_value=ours_f,
                            theirs_value=theirs_f,
                            description=f"Conflict on asset '{asset_key}' property '{field}'",
                        )
                    )
                    merged[field] = ours_f

        return merged, conflicts

    @classmethod
    def _merge_subdict(
        cls,
        prefix: str,
        base: Dict[str, Any],
        ours: Dict[str, Any],
        theirs: Dict[str, Any],
    ) -> Tuple[Dict[str, Any], List[FieldConflict]]:
        merged: Dict[str, Any] = {}
        conflicts: List[FieldConflict] = []

        all_sub_keys = set(base.keys()) | set(ours.keys()) | set(theirs.keys())
        for k in sorted(all_sub_keys):
            bv = base.get(k)
            ov = ours.get(k)
            tv = theirs.get(k)

            if ov == tv:
                merged[k] = ov
            elif bv == ov:
                merged[k] = tv
            elif bv == tv:
                merged[k] = ov
            else:
                conflicts.append(
                    FieldConflict(
                        path=f"{prefix}.{k}",
                        base_value=bv,
                        ours_value=ov,
                        theirs_value=tv,
                        description=f"Conflict on {prefix}.{k}",
                    )
                )
                merged[k] = ov

        return merged, conflicts

    @classmethod
    def _merge_strategies(
            cls,
            asset_key: str,
            base: List[Dict[str, Any]],
            ours: List[Dict[str, Any]],
            theirs: List[Dict[str, Any]],
    ) -> Tuple[List[Dict[str, Any]], List[FieldConflict]]:
        if ours == theirs:
            return copy.deepcopy(ours), []
        if base == ours:
            return copy.deepcopy(theirs), []
        if base == theirs:
            return copy.deepcopy(ours), []

        # Compare strategy lists by name or action
        base_map = {s.get("name", str(i)): s for i, s in enumerate(base)}
        ours_map = {s.get("name", str(i)): s for i, s in enumerate(ours)}
        theirs_map = {s.get("name", str(i)): s for i, s in enumerate(theirs)}

        all_names = list(dict.fromkeys(list(ours_map.keys()) + list(theirs_map.keys()) + list(base_map.keys())))
        merged_strategies: List[Dict[str, Any]] = []
        conflicts: List[FieldConflict] = []

        for name in all_names:
            bs = base_map.get(name)
            os_val = ours_map.get(name)
            ts = theirs_map.get(name)

            if os_val == ts:
                if os_val is not None:
                    merged_strategies.append(os_val)
            elif bs == os_val:
                if ts is not None:
                    merged_strategies.append(ts)
            elif bs == ts:
                if os_val is not None:
                    merged_strategies.append(os_val)
            else:
                conflicts.append(
                    FieldConflict(
                        path=f"assets.{asset_key}.strategies.{name}",
                        base_value=bs,
                        ours_value=os_val,
                        theirs_value=ts,
                        description=f"Conflicting strategy definition '{name}' on asset '{asset_key}'",
                    )
                )
                if os_val is not None:
                    merged_strategies.append(os_val)

        return merged_strategies, conflicts
