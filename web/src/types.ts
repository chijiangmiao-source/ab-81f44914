export interface ChannelInput {
  id: string;
  source: string;
  target: string;
  cost: number;
}

export interface SolveRequest {
  points: string[];
  root: string;
  channels: ChannelInput[];
}

export interface TreeEdge {
  channel_id: string;
  source: string;
  target: string;
  cost: number;
}

export interface ChoiceRecord {
  target: string;
  source: string;
  channel_id: string;
  reduced_cost_part: number;
  perturbed_weight: string;
}

export interface FollowRecord {
  from: string;
  to: string;
  channel_id: string;
}

export interface RoundRecord {
  depth: number;
  choices: ChoiceRecord[];
  cycle?: {
    nodes: string[];
    channel_ids: string[];
    follow: FollowRecord[];
    cycle_cost: number;
  };
  contraction?: {
    supernode: string;
    cycle_nodes: string[];
    original_points: string[];
    cycle_channel_ids: string[];
    cycle_cost: number;
  };
}

export interface ExpansionRecord {
  depth: number;
  supernode: string;
  cycle_nodes: string[];
  removed_channel_id: string;
  added_channel_id: string;
  entered_point: string;
  external_source: string;
}

export interface SolveResponse {
  ok: boolean;
  points?: string[];
  root?: string;
  tree?: {
    total_cost: number;
    channel_ids: string[];
    edges: TreeEdge[];
  };
  evidence?: {
    perturbation: Record<string, string>;
    rounds: RoundRecord[];
    expansions: ExpansionRecord[];
  };
  unreachable: string[];
  error?: { code: string; message: string; field?: string };
}
