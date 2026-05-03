/**
 * WebMCP 브라우저 API 타입 정의 (ambient).
 *
 * 표준화 진행 중인 navigator.modelContext.registerTool() 인터페이스.
 * spec: https://webmachinelearning.github.io/webmcp/
 */

export interface ModelContextToolAnnotations {
  readOnlyHint?: boolean;
  untrustedContentHint?: boolean;
}

export interface ModelContextTool<Input = unknown, Output = unknown> {
  name: string;
  title?: string;
  description: string;
  inputSchema: object;
  execute: (input: Input, client: unknown) => Promise<Output>;
  annotations?: ModelContextToolAnnotations;
}

export interface ModelContextRegisterOptions {
  signal?: AbortSignal;
}

export interface ModelContext {
  registerTool: (
    tool: ModelContextTool,
    options?: ModelContextRegisterOptions,
  ) => void;
}

declare global {
  interface Navigator {
    modelContext?: ModelContext;
  }
}
