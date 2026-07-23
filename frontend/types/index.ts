export interface UserOut {
  id: string;
  display_name: string | null;
  coins: number;
  is_admin: boolean;
  couple_id: string | null;
  total_games: number;
  best_match_streak: number;
}

export interface QuestionOut {
  id: number;
  text: string;
  category: string;
  average_rating: number;
  rating_count: number;
}

export interface CoupleOut {
  id: string;
  invite_code: string;
  status: "pending" | "active";
  members: UserOut[];
}

export interface AnswerOut {
  user_id: string;
  text: string;
}

export interface HistoryItemOut {
  round_id: number;
  question_text: string;
  answers: AnswerOut[];
  is_match: boolean;
  completed_at: string | null;
}

export interface AchievementOut {
  code: string;
  title: string;
  description: string;
  coin_reward: number;
  earned_at?: string;
}

// ---------- WebSocket message shapes ----------

export type WsServerMessage =
  | {
      action: "round_started";
      round_id: number;
      question: { id: number; text: string; category: string };
      first_responder_id: string;
      second_responder_id: string;
    }
  | { action: "answer_saved"; round_id: number }
  | { action: "your_turn"; round_id: number }
  | {
      action: "round_result";
      round_id: number;
      question: { id: number; text: string; category: string };
      answers: AnswerOut[];
      is_match: boolean;
      points_awarded: number;
      coins_awarded: number;
    }
  | {
      action: "new_achievement";
      achievement: { code: string; title: string; description: string; coin_reward: number };
    }
  | { action: "error"; detail: string };

export type WsClientMessage =
  | { action: "start_round" }
  | { action: "submit_answer"; round_id: number; text: string };
