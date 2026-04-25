export interface FeedbackStats {
  total: number;
  likes: number;
  dislikes: number;
  satisfaction_rate: number;
  dislike_tags: Record<string, number>;
}
