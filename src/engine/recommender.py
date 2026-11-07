class Recommender:
    """Scores and ranks champion picks based on counters, synergy, tier, and win rate."""

    TIER_SCORE = {"S": 12, "A": 9, "B": 6, "C": 3, "D": 1}

    def __init__(self, store):
        self.store = store

    def recommend(self, role, allies, enemies, banned=None, owned=None, personal=None, prefer_owned=True):
        """Rank picks vs enemy comp, preferring owned champs and high WR (global/personal)."""
        banned = set(banned or [])
        taken = set(allies) | set(enemies) | banned
        owned_set = set(owned or [])
        personal = personal or {}
        candidates = self.store.champions_for_role(role)
        # If caller provided ownership info and wants owned preference, keep all but score owned much higher.
        has_ownership = len(owned_set) > 0

        scored = []
        for name, data in candidates:
            if name in taken:
                continue

            score = 0.0
            reasons = []
            is_owned = (not has_ownership) or (name in owned_set)

            if has_ownership and is_owned:
                score += 14
                reasons.append("Owned")
            elif has_ownership and prefer_owned:
                score -= 6

            counter_sum = 0
            countered_names = []
            for enemy in enemies:
                ms = self.store.get_matchup_score(name, enemy)
                counter_sum += ms
                if ms >= 1:
                    countered_names.append(enemy)
            if enemies:
                score += (counter_sum / max(len(enemies), 1)) * 18
            if countered_names:
                reasons.append(f"Good vs {', '.join(countered_names[:2])}")
            if counter_sum < -2:
                reasons.append("Risky vs enemy comp")

            synergy_list = self.store.get_synergies(name)
            matched = [a for a in allies if a in synergy_list]
            score += len(matched) * 8
            if matched:
                reasons.append(f"Synergy with {', '.join(matched[:2])}")

            tier = self.store.get_tier(name, role)
            tier_pts = self.TIER_SCORE.get(tier, 5)
            score += tier_pts
            if tier in ("S", "A"):
                reasons.append(f"{tier}-tier")

            build = self.store.get_build(name, role)
            global_wr = build.get("wr") if build else None
            if global_wr is not None:
                if global_wr > 52:
                    score += (global_wr - 50) * 1.8
                    reasons.append(f"{global_wr}% WR")
                elif global_wr > 50.5:
                    score += (global_wr - 50) * 1.0

            p = personal.get(name) or {}
            pg = p.get("games") or 0
            pwr = p.get("wr")
            if pg >= 2 and pwr is not None:
                score += (pwr - 50) * 0.45
                reasons.append(f"Your WR {pwr}% ({pg}g)")

            build_preview = {}
            if build:
                build_preview = {
                    "keystone": (build.get("runes") or [""])[0],
                    "trees": build.get("rune_trees", []),
                    "core": build.get("core", []),
                    "boots": build.get("boots", ""),
                    "spells": build.get("spells", []),
                    "skills": build.get("skills", ""),
                    "wr": build.get("wr"),
                }

            scored.append({
                "champion": name,
                "score": round(score, 1),
                "tier": tier,
                "roles": data.get("roles", []),
                "owned": bool(is_owned) if has_ownership else None,
                "personal": {"wr": pwr, "games": pg} if pg else None,
                "reasons": reasons or ["Solid pick"],
                "build": build_preview,
            })

        scored.sort(key=lambda x: (x.get("owned") is not False, x["score"]), reverse=True)
        return scored[:10]
