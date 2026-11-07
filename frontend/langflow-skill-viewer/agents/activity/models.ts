
export type Run = {provider?:string;id:string;node:string;node_label?:string|null;execution:string|null;started:string;ended:string|null;status:string;stream_state:string;reason?:string|null;runner_run_id:string|null;native_session:string|null;model:string|null;event_count:number};

export type Lane = {id:string;thread?:string;turn?:string;started:string;ended:string|null;status?:string;usage?:Record<string,number>|null;cost?:Cost;item?:Record<string,unknown>;conflicting_receipts?:boolean};

export type Cost = {amount:number|null;currency:string;basis:string;catalog_date:string;source:string|null;model?:string|null;per_thread?:Record<string,Cost>;reason?:string|null};

export type Projection = {turns:Lane[];items:Lane[];threads:{id:string;parent:string|null;title?:string}[];usage_by_thread?:Record<string,Record<string,number>|null>;usage:Record<string,number>|null;usage_points:{at:string;thread:string;turn?:string;turn_usage?:Record<string,number>|null;turn_cost?:Cost;usage:Record<string,number>;cost:Cost}[];clock:string;cost:Cost;cost_reason:string;telemetry:Record<string,unknown>[];telemetry_coverage:string;diagnostics?:Record<string,unknown>[]};

export type Detail = {run:Run;projection:Projection;truncated:boolean};

export type ExportContext = {graph_id?:string;run_id:string;execution_id:string|null;node_id:string;provider?:string;model:string|null;native_session:string|null;scope:ActivityScope;capture_state:string;capture_reason?:string|null;truncated:boolean};

export type UsagePoint = Projection["usage_points"][number];

export type ChartPoint = {at:string;usage:Record<string,number>|null;cost:number|null};

export type ActivityScope = {thread?:string;turn?:string};
