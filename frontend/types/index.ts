export interface UserOut {
  id: string;
  display_name: string | null;
  username: string | null;
  coins: number;
  is_admin: boolean;
  couple_id: string | null;
  total_games: number;
  best_match_streak: number;
}

export type QuestionType = "open" | "choice";

export interface QuestionOptionOut {
  id: number;
  text: string;
}

export interface QuestionOut {
  id: number;
  text: string;
  category: string;
  question_type: QuestionType;
  options: QuestionOptionOut[];
  average_rating: number;
  rating_count: number;
}

export interface CoupleOut {
  id: string;
  invite_code: string;
  status: "pending" | "active" | "disbanded";
  members: UserOut[];
}

export interface PackOut {
  id: number;
  name: string;
  description: string | null;
  price_coins: number;
  is_default: boolean;
  question_count: number;
  unlocked: boolean;
}

export interface AnswerOut {
  user_id: string;
  text: string;
  selected_option_id: number | null;
}

export interface HistoryItemOut {
  round_id: number;
  question_text: string;
  question_type: QuestionType;
  answerer_id: string;
  guesser_id: string;
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

// ---------- Admin / pack moderation ----------

export type PackStatus = "pending" | "approved" | "rejected";

export interface PackAdminOut {
  id: number;
  name: string;
  description: string | null;
  price_coins: number;
  is_default: boolean;
  status: PackStatus;
  is_active: boolean;
  created_by_id: string | null;
  rejection_reason: string | null;
  question_count: number;
}

export interface PackAdminDetailOut extends PackAdminOut {
  questions: QuestionOut[];
}

export interface PackQuestionOptionIn {
  text: string;
}

export interface PackQuestionIn {
  text: string;
  category?: string;
  question_type: QuestionType;
  options?: PackQuestionOptionIn[];
}

export interface PackUploadRequest {
  name: string;
  description?: string;
  price_coins?: number;
  questions: PackQuestionIn[];
}

// ---------- WebSocket message shapes ----------

export interface RoundQuestionPayload {
  id: number;
  text: string;
  category: string;
  question_type: QuestionType;
  options: QuestionOptionOut[];
}

export type WsServerMessage =
  | { action: "round_proposed"; pack_id: number; pack_name: string; proposer_id: string }
  | { action: "round_declined"; pack_id: number }
  | {
      action: "round_started";
      round_id: number;
      question: RoundQuestionPayload;
      answerer_id: string;
      guesser_id: string;
    }
  | { action: "answer_saved"; round_id: number }
  | { action: "your_turn"; round_id: number }
  | { action: "awaiting_validation"; round_id: number }
  | { action: "validate_request"; round_id: number; your_answer: string; guess: string }
  | {
      action: "round_result";
      round_id: number;
      question: RoundQuestionPayload;
      answers: AnswerOut[];
      answerer_id: string;
      guesser_id: string;
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
  | { action: "propose_round"; pack_id: number }
  | { action: "respond_round_proposal"; pack_id: number; accept: boolean }
  | { action: "submit_answer"; round_id: number; text: string; option_id?: number | null }
  | { action: "validate_answer"; round_id: number; is_match: boolean };
