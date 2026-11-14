# Reinforcement Learning Pre-Trip Itinerary Planner using Contextual LinUCB
# Implements disjoint contextual multi-armed bandits with explicit vs. implicit rewards,
# hard safety constraints, temporary vs. persistent preference handling, and SQLite persistence.

import json
import math
import numpy as np
from typing import List, Dict, Any, Optional, Tuple

FEATURE_DIMENSION = 24

FEATURE_NAMES = [
    # User Profile (0..7)
    "user_interest_culture",
    "user_interest_nature",
    "user_interest_food",
    "user_interest_adventure",
    "user_interest_relaxation",
    "user_interest_shopping",
    "user_interest_photography",
    "user_interest_architecture",
    # User Comfort & Pacing (8..11)
    "user_pace_slider",
    "user_crowd_tolerance",
    "user_budget_weight",
    "user_walking_tolerance",
    # Trip Context (12..14)
    "trip_duration_norm",
    "trip_daily_budget_norm",
    "trip_pace_index",
    # Slot Context (15..18)
    "slot_day_progression",
    "slot_is_morning",
    "slot_is_afternoon",
    "slot_is_evening",
    # Activity Attributes (19..23)
    "activity_category_match",
    "activity_physical_intensity",
    "activity_crowd_level",
    "activity_cost_norm",
    "activity_proximity_bonus"
]

CANONICAL_ARMS = [
    "culture_history",
    "nature_outdoors",
    "food_dining",
    "adventure",
    "relaxation",
    "shopping_local",
    "scenic"
]

class LinUCBPolicy:
    """Disjoint Contextual Linear Bandit Policy for activity-level itinerary recommendations."""

    def __init__(self, user_id: str, alpha: float = 0.5):
        self.user_id = user_id
        self.alpha = alpha # Exploration trade-off parameter
        self.dimension = FEATURE_DIMENSION
        self.arms: Dict[str, Dict[str, Any]] = {}

        for arm in CANONICAL_ARMS:
            self._init_arm(arm)

    def _init_arm(self, arm_id: str):
        # A_a is d x d identity matrix; A_inv is d x d identity matrix; b_a is d x 1 zero vector
        self.arms[arm_id] = {
            "A": np.eye(self.dimension, dtype=float),
            "A_inv": np.eye(self.dimension, dtype=float),
            "b": np.zeros(self.dimension, dtype=float),
            "pull_count": 0,
            "total_reward": 0.0
        }

    def predict_score(self, arm_id: str, context: np.ndarray) -> Tuple[float, float, float]:
        """Returns (total_score, exploitation_term, exploration_bonus) in O(d^2) using maintained A_inv."""
        if arm_id not in self.arms:
            self._init_arm(arm_id)

        arm_data = self.arms[arm_id]
        if "A_inv" not in arm_data:
            try:
                arm_data["A_inv"] = np.linalg.inv(arm_data["A"])
            except np.linalg.LinAlgError:
                arm_data["A_inv"] = np.linalg.pinv(arm_data["A"])

        A_inv = arm_data["A_inv"]
        b = arm_data["b"]

        theta = A_inv.dot(b)
        exploitation = float(np.dot(theta, context))
        variance = float(np.dot(context, A_inv.dot(context)))
        exploration = self.alpha * math.sqrt(max(0.0, variance))
        total_score = exploitation + exploration
        return total_score, exploitation, exploration

    def update(self, arm_id: str, context: np.ndarray, reward: float):
        """
        Update arm covariance matrix and bias vector using closed-form Sherman-Morrison rank-1 updates.
        Maintains inverse covariance matrix A_inv directly in O(d^2) time via:
            A_inv <- A_inv - (A_inv @ x @ x^T @ A_inv) / (1 + x^T @ A_inv @ x)
        """
        if arm_id not in self.arms:
            self._init_arm(arm_id)

        arm_data = self.arms[arm_id]
        if "A_inv" not in arm_data:
            try:
                arm_data["A_inv"] = np.linalg.inv(arm_data["A"])
            except np.linalg.LinAlgError:
                arm_data["A_inv"] = np.linalg.pinv(arm_data["A"])

        # Incremental Sherman-Morrison rank-1 update of inverse covariance matrix
        A_inv = arm_data["A_inv"]
        v = A_inv.dot(context)
        denom = 1.0 + float(np.dot(context, v))
        if abs(denom) > 1e-12:
            arm_data["A_inv"] -= np.outer(v, v) / denom

        # A_a <- A_a + x * x^T
        arm_data["A"] += np.outer(context, context)
        # b_a <- b_a + r * x
        arm_data["b"] += reward * context
        arm_data["pull_count"] += 1
        arm_data["total_reward"] += reward

    def get_arm_weights(self, arm_id: str) -> np.ndarray:
        if arm_id not in self.arms:
            return np.zeros(self.dimension)
        arm_data = self.arms[arm_id]
        if "A_inv" in arm_data:
            return arm_data["A_inv"].dot(arm_data["b"])
        try:
            A_inv = np.linalg.inv(arm_data["A"])
        except np.linalg.LinAlgError:
            A_inv = np.linalg.pinv(arm_data["A"])
        return A_inv.dot(arm_data["b"])


# ---------------------------------------------------------------------------
# Feature Extraction
# ---------------------------------------------------------------------------

def extract_context_vector(
    user_profile: Dict[str, Any],
    trip_config: Dict[str, Any],
    day_number: int,
    total_days: int,
    time_slot: str,
    activity: Dict[str, Any],
    preceding_activity: Optional[Dict[str, Any]] = None
) -> np.ndarray:
    """Constructs the 24-dimensional continuous feature context vector."""
    x = np.zeros(FEATURE_DIMENSION, dtype=float)

    # 1. User Profile interests (0..7)
    user_interests = set(user_profile.get("interests", []))
    for g in user_profile.get("travel_goals", []) + user_profile.get("place_interests", []):
        user_interests.add(g)

    interest_keys = [
        ("culture", 0), ("history", 0), ("nature", 1), ("outdoor", 1),
        ("food", 2), ("dining", 2), ("adventure", 3), ("relaxation", 4),
        ("shopping", 5), ("photography", 6), ("architecture", 7)
    ]
    for key, idx in interest_keys:
        if any(key in item for item in user_interests):
            x[idx] = 1.0

    # 2. Comfort & Pacing (8..11)
    x[8] = float(user_profile.get("pace", 0.5))
    x[9] = float(user_profile.get("crowd_tolerance", 0.5))
    budget_map = {"very_budget": 0.1, "budget": 0.25, "balanced": 0.6, "mid_range": 0.6, "premium": 0.85, "luxury": 1.0}
    x[10] = budget_map.get(str(user_profile.get("budget_tier", "balanced")), 0.5)
    walk_map = {"low": 0.2, "medium": 0.6, "high": 1.0}
    x[11] = walk_map.get(str(user_profile.get("walking_tolerance", "medium")), 0.6)

    # 3. Trip Context (12..14)
    duration_days = max(1, trip_config.get("duration_days", total_days))
    x[12] = min(1.0, duration_days / 14.0)
    total_budget = float(trip_config.get("total_budget", 1000.0))
    daily_budget = total_budget / duration_days
    x[13] = min(1.0, daily_budget / 500.0)
    pace_map = {"relaxed": 0.3, "balanced": 0.6, "packed": 1.0}
    x[14] = pace_map.get(str(trip_config.get("travel_pace", "balanced")), 0.6)

    # 4. Slot Context (15..18)
    x[15] = float(day_number) / max(1.0, float(total_days))
    if time_slot == "morning":
        x[16] = 1.0
    elif time_slot == "afternoon":
        x[17] = 1.0
    elif time_slot == "evening":
        x[18] = 1.0

    # 5. Activity Attributes (19..23)
    act_cat = activity.get("category", "")
    act_tags = activity.get("tags", [])
    if isinstance(act_tags, str):
        try:
            act_tags = json.loads(act_tags)
        except Exception:
            act_tags = [act_tags]

    # Category match
    cat_match = 0.0
    for tag in act_tags:
        for u_int in user_interests:
            if tag in u_int or u_int in tag:
                cat_match += 0.3
    x[19] = min(1.0, cat_match)

    # Physical intensity
    intensity_map = {"low": 0.2, "moderate": 0.6, "high": 1.0}
    x[20] = intensity_map.get(activity.get("physical_intensity", "moderate"), 0.5)

    # Crowd level
    crowd_map = {"low": 0.2, "moderate": 0.6, "high": 1.0}
    x[21] = crowd_map.get(activity.get("crowd_level", "moderate"), 0.5)

    # Activity Cost
    from app.core.assumptions import UNKNOWN_ENTRY_INR
    raw_cost = activity.get('cost_amount')
    cost_amount = float(raw_cost) if raw_cost is not None else UNKNOWN_ENTRY_INR
    x[22] = min(1.0, cost_amount / 120.0)

    # Proximity bonus with preceding activity
    if preceding_activity:
        p_neigh = preceding_activity.get("neighborhood", "")
        a_neigh = activity.get("neighborhood", "")
        if p_neigh and a_neigh and p_neigh == a_neigh:
            x[23] = 1.0
        else:
            p_lat = preceding_activity.get("latitude")
            p_lon = preceding_activity.get("longitude")
            a_lat = activity.get("latitude")
            a_lon = activity.get("longitude")
            if p_lat and p_lon and a_lat and a_lon:
                dist = math.sqrt((p_lat - a_lat)**2 + (p_lon - a_lon)**2)
                # approx degree distance
                x[23] = max(0.0, 1.0 - (dist / 0.15))
            else:
                x[23] = 0.5
    else:
        x[23] = 0.5

    return x


# ---------------------------------------------------------------------------
# Hard Constraints & Safety Masking
# ---------------------------------------------------------------------------

def is_activity_safe_and_valid(
    activity: Dict[str, Any],
    user_profile: Dict[str, Any],
    trip_exclusions: set
) -> Tuple[bool, str]:
    """
    Evaluates hard safety, dietary, mobility, and trip exclusion constraints.
    Returns (is_valid, rejection_reason_if_invalid).
    """
    act_id = activity.get("id") or activity.get("activity_id")
    if act_id in trip_exclusions:
        return False, "Excluded by user in this trip"

    # 1. Avoidance triggers against user profile avoidances
    avoidances = set(user_profile.get("avoidances", []))
    act_triggers = activity.get("avoidance_triggers", [])
    if isinstance(act_triggers, str):
        try:
            act_triggers = json.loads(act_triggers)
        except Exception:
            act_triggers = [act_triggers]

    for trigger in act_triggers:
        if trigger in avoidances:
            return False, f"Violates safety/avoidance constraint: {trigger}"

    # 2. Walking and mobility limits
    walking_tolerance = user_profile.get("walking_tolerance", "medium")
    if walking_tolerance == "low" and activity.get("physical_intensity") == "high":
        return False, "Exceeds low walking/mobility capacity"

    # 3. Dietary requirements (for food & dining activities)
    dietary_needs = set(user_profile.get("dietary", []))
    if "vegan" in dietary_needs or "halal" in dietary_needs or "vegetarian" in dietary_needs:
        # Dining places must respect explicit dietary exclusions
        act_desc = (activity.get("description", "") + " " + activity.get("name", "")).lower()
        if "steakhouse" in act_desc and "vegetarian" in dietary_needs:
            return False, "Incompatible with dietary requirements"

    return True, "Valid"


# ---------------------------------------------------------------------------
# Policy Persistence (SQLite)
# ---------------------------------------------------------------------------

def load_user_policy(conn, user_id: str) -> LinUCBPolicy:
    """Loads the user's LinUCB policy parameters from SQLite or returns a freshly initialized policy."""
    policy = LinUCBPolicy(user_id=user_id)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT arm_id, dimension, matrix_a_json, vector_b_json, pull_count, total_reward
        FROM rl_user_policies
        WHERE user_id = ?
    """, (user_id,))
    rows = cursor.fetchall()

    for row in rows:
        arm_id = row[0]
        dim = row[1]
        if dim == FEATURE_DIMENSION:
            try:
                A = np.array(json.loads(row[2]), dtype=float)
                b = np.array(json.loads(row[3]), dtype=float)
                pull_count = row[4]
                # Check for total_reward column safely
                tot_reward = row[5] if len(row) > 5 and row[5] is not None else 0.0
                try:
                    A_inv = np.linalg.inv(A)
                except Exception:
                    A_inv = np.linalg.pinv(A)
                policy.arms[arm_id] = {
                    "A": A,
                    "A_inv": A_inv,
                    "b": b,
                    "pull_count": pull_count,
                    "total_reward": tot_reward
                }
            except Exception:
                pass

    return policy

def save_user_policy(conn, policy: LinUCBPolicy):
    """Saves the LinUCB policy parameters to SQLite."""
    cursor = conn.cursor()
    for arm_id, arm_data in policy.arms.items():
        matrix_a_json = json.dumps(arm_data["A"].tolist())
        vector_b_json = json.dumps(arm_data["b"].tolist())
        pull_count = arm_data["pull_count"]
        tot_reward = arm_data.get("total_reward", 0.0)

        cursor.execute("""
            INSERT INTO rl_user_policies (
                user_id, arm_id, dimension, matrix_a_json, vector_b_json, pull_count, total_reward, last_updated
            ) VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(user_id, arm_id) DO UPDATE SET
                matrix_a_json = excluded.matrix_a_json,
                vector_b_json = excluded.vector_b_json,
                pull_count = excluded.pull_count,
                total_reward = excluded.total_reward,
                last_updated = CURRENT_TIMESTAMP
        """, (
            policy.user_id,
            arm_id,
            policy.dimension,
            matrix_a_json,
            vector_b_json,
            pull_count,
            tot_reward
        ))
    conn.commit()


# ---------------------------------------------------------------------------
# Feedback & Reward Processing
# ---------------------------------------------------------------------------

def process_activity_feedback(
    conn,
    user_id: str,
    trip_id: str,
    itinerary_id: str,
    activity_id: str,
    action_type: str, # 'accept', 'reject', 'modify'
    rejection_reason: Optional[str] = None,
    is_trip_specific: bool = False,
    is_implicit: bool = False,
    occurrence_id: Optional[str] = None,
    commit: bool = True,
) -> Dict[str, Any]:
    """
    Executes reward calculation, policy update, feedback logging, and status update.
    Distinguishes temporary trip-specific rejections from long-term preference updates.
    """
    cursor = conn.cursor()

    # Retrieve activity and itinerary details
    where = 'ia.id = ?' if occurrence_id else 'ia.activity_id = ?'
    cursor.execute(f"""
        SELECT ia.category, ia.neighborhood, ia.duration_minutes, ia.cost_estimate,
               ia.day_number, i.total_days, t.destination_id, ia.status, ia.id, ia.activity_id
        FROM itinerary_activities ia
        JOIN itineraries i ON ia.itinerary_id = i.id
        JOIN trips t ON i.trip_id = t.id
        WHERE ia.itinerary_id = ? AND {where}
    """, (itinerary_id, occurrence_id or activity_id))
    row = cursor.fetchone()

    if not row:
        raise ValueError("Activity not found in specified itinerary")
    if occurrence_id and row[9] != activity_id:
        raise ValueError('The occurrence does not match the selected catalogue activity.')
    if not occurrence_id:
        cursor.execute('SELECT COUNT(*) FROM itinerary_activities WHERE itinerary_id=? AND activity_id=?',
                       (itinerary_id, activity_id))
        if cursor.fetchone()[0] > 1:
            raise ValueError('This place occurs more than once. Supply its itinerary occurrence ID.')

    desired_status = {'accept':'accepted','reject':'rejected','modify':'modified'}.get(action_type.lower())
    if desired_status is None:
        raise ValueError('Choose accept, reject or modify.')
    if row[7] == desired_status:
        return {'status':'unchanged','action_type':action_type,'new_status':desired_status,
                'reward_assigned':0.0,'is_trip_specific':is_trip_specific,'policy_updated':False}
    category = row[0]
    cost_est = row[3]
    day_num = row[4]
    total_days = row[5]

    # Load user profile for context extraction
    cursor.execute("SELECT interests, pace, crowd_tolerance, budget_tier FROM traveller_profiles WHERE user_id = ?", (user_id,))
    prof_row = cursor.fetchone()
    user_prof = dict(prof_row) if prof_row else {}
    if "interests" in user_prof and isinstance(user_prof["interests"], str):
        try:
            user_prof["interests"] = json.loads(user_prof["interests"])
        except Exception:
            user_prof["interests"] = []

    cursor.execute("SELECT avoidances, walking_tolerance, dietary FROM detailed_profiles WHERE user_id = ?", (user_id,))
    det_row = cursor.fetchone()
    if det_row:
        user_prof["avoidances"] = json.loads(det_row["avoidances"]) if det_row["avoidances"] else []
        user_prof["walking_tolerance"] = det_row["walking_tolerance"]
        user_prof["dietary"] = json.loads(det_row["dietary"]) if det_row["dietary"] else []

    context_x = extract_context_vector(
        user_profile=user_prof,
        trip_config={"duration_days": total_days},
        day_number=day_num,
        total_days=total_days,
        time_slot="afternoon",
        activity={"category": category, "cost_amount": cost_est, "tags": [category]}
    )

    # 1. Determine Reward Value (Clear attribution, no double-counting)
    if action_type.lower() == "accept":
        reward = 1.0 if not is_implicit else 0.2
        new_status = "accepted"
    elif action_type.lower() == "reject":
        reward = -1.0
        new_status = "rejected"
    elif action_type.lower() == "modify":
        reward = -0.4 # mild dissatisfaction with slot suggestion
        new_status = "modified"
    else:
        reward = 0.0
        new_status = "proposed"

    # 2. Update LinUCB Policy (Only if NOT trip-specific or if general preference)
    policy_updated = False
    policy = load_user_policy(conn, user_id)

    if not is_trip_specific:
        # Permanent preference update
        arm_id = category if category in CANONICAL_ARMS else "culture_history"
        policy.update(arm_id, context_x, reward)
        save_user_policy(conn, policy)
        policy_updated = True

    # 3. Update Activity Status in database
    cursor.execute("""
        UPDATE itinerary_activities
        SET status = ?, rejection_reason = ?
        WHERE itinerary_id = ? AND id = ?
    """, (new_status, rejection_reason, itinerary_id, row[8]))

    # 4. Insert into RL Feedback Log
    cursor.execute("""
        INSERT INTO rl_feedback_log (
            id, user_id, trip_id, itinerary_id, activity_id, arm_id,
            action_type, rejection_reason, is_trip_specific, is_implicit,
            reward, context_vector_json
        ) VALUES (hex(randomblob(16)), ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        user_id,
        trip_id,
        itinerary_id,
        activity_id,
        category,
        action_type.lower(),
        rejection_reason,
        1 if is_trip_specific else 0,
        1 if is_implicit else 0,
        reward,
        json.dumps(context_x.tolist())
    ))
    if commit:
        conn.commit()

    return {
        "status": "success",
        "action_type": action_type,
        "new_status": new_status,
        "reward_assigned": reward,
        "is_trip_specific": is_trip_specific,
        "policy_updated": policy_updated
    }
