class Recommender:
    """Scores and ranks champion picks based on counters, synergy, tier, and win rate."""

    TIER_SCORE = {"S": 12, "A": 9, "B": 6, "C": 3, "D": 1}

    def __init__(self, store):
        self.store = store

    def recommend(self, role, allies, enemies, banned=None):
        banned = set(banned or [])
        taken = set(allies) | set(enemies) | banned
        candidates = self.store.champions_for_role(role)

        scored = []
        for name, data in candidates:
            if name in taken:
                continue

            score = 0.0
            reasons = []

            counter_sum = 0
            countered_names = []
            for enemy in enemies:
                ms = self.store.get_matchup_score(name, enemy)
                counter_sum += ms
                if ms >= 1:
                    countered_names.append(enemy)
            if enemies:
                score += (counter_sum / len(enemies)) * 18
            if countered_names:
                reasons.append(f"Counters {', '.join(countered_names[:2])}")
            if counter_sum < -2:
                reasons.append("Countered by enemy comp")

            synergy_list = self.store.get_synergies(name)
            matched = [a for a in allies if a in synergy_list]
            score += len(matched) * 8
            if matched:
                reasons.append(f"Synergy with {', '.join(matched[:2])}")

            tier = self.store.get_tier(name, role)
            tier_pts = self.TIER_SCORE.get(tier, 5)
            score += tier_pts
            if tier in ("S", "A"):
                reasons.append(f"{tier}-tier pick")

            build = self.store.get_build(name, role)
            if build:
                wr = build.get("wr", 50)
                if wr > 52:
                    score += (wr - 50) * 2
                    reasons.append(f"{wr}% WR")
                elif wr > 50.5:
                    score += (wr - 50)

            build_preview = {}
            if build:
                build_preview = {
                    "keystone": (build.get("runes") or [""])[0],
                    "trees": build.get("rune_trees", []),
                    "core": build.get("core", []),
                    "boots": build.get("boots", ""),
                    "spells": build.get("spells", []),
                    "skills": build.get("skills", ""),
                    "wr": build.get("wr", 0),
                }

            scored.append({
                "champion": name,
                "score": round(score, 1),
                "tier": tier,
                "roles": data.get("roles", []),
                "reasons": reasons or ["Solid pick"],
                "build": build_preview,
            })

        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored[:10]
