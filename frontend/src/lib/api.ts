/**
 * 백엔드 API 호출 유틸리티
 * JWT Access Token을 자동으로 포함하고, 만료 시 Refresh Token으로 갱신.
 */

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export async function apiFetch<T>(
  path: string,
  options: RequestInit & { accessToken?: string } = {},
): Promise<T> {
  const { accessToken, ...fetchOptions } = options;

  const headers = new Headers(fetchOptions.headers);

  // FormData는 브라우저가 Content-Type을 자동 설정
  // body가 있고 JSON인 경우에만 application/json 설정 (body 없는 DELETE 등에는 불필요)
  if (fetchOptions.body && !(fetchOptions.body instanceof FormData) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  if (accessToken) {
    headers.set("Authorization", `Bearer ${accessToken}`);
  }

  const res = await fetch(`${API_BASE}${path}`, {
    ...fetchOptions,
    headers,
  });

  if (!res.ok) {
    const error = await res.json().catch(() => ({ detail: "요청에 실패했습니다." }));
    throw new ApiError(res.status, error.detail || "요청에 실패했습니다.");
  }

  // 204 No Content
  if (res.status === 204) {
    return undefined as T;
  }

  return res.json();
}
