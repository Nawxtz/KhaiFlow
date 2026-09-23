export interface OrderItem {
  id: number;
  order_id: string;
  shop_id?: string | null;
  sku: string;
  name: string;
  size?: string | null;
  qty: number;
  unit_price: number | string;
  line_total: number | string;
}

export interface Order {
  id: string;
  shop_id?: string | null;
  line_user_id: string;
  status: string;
  total: number | string;
  currency: string;
  created_at: string;
  updated_at: string;
  ttl_expires_at?: string | null;
  approval_state?: string | null;
  payment_ref?: string | null;
  risk_score?: number | null;
  items?: OrderItem[];
}

export interface ManualActionResponse {
  status: string;
  order_id: string;
  order_status: string;
  approval_state?: string | null;
  message?: string | null;
}

export interface InventoryItem {
  sku: string;
  shop_id?: string | null;
  name: string;
  category: string;
  price: number;
  image_url?: string | null;
  stock: number;
  reserved: number;
  available_stock: number;
  active: boolean;
  version: number;
}

export class ApiError extends Error {
  status: number;
  detail: string;

  constructor(status: number, detail: string) {
    super(`API Error ${status}: ${detail}`);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const url = `${API_BASE_URL}${path}`;
  const headers = {
    "Content-Type": "application/json",
    Accept: "application/json",
    ...options.headers,
  };

  const response = await fetch(url, {
    ...options,
    headers,
  });

  if (!response.ok) {
    let detail = response.statusText;
    try {
      const errJson = await response.json();
      if (errJson && errJson.detail) {
        detail = typeof errJson.detail === "string" ? errJson.detail : JSON.stringify(errJson.detail);
      }
    } catch {
      // ignore
    }
    throw new ApiError(response.status, detail);
  }

  return response.json() as Promise<T>;
}

export const api = {
  async getOrders(params?: { shop_id?: string; status?: string }): Promise<Order[]> {
    const query = new URLSearchParams();
    if (params?.shop_id) query.set("shop_id", params.shop_id);
    if (params?.status && params.status !== "ALL") query.set("status", params.status);
    const queryString = query.toString() ? `?${query.toString()}` : "";
    return request<Order[]>(`/api/orders${queryString}`);
  },

  async getOrder(id: string, shop_id?: string): Promise<Order> {
    const query = new URLSearchParams();
    if (shop_id) query.set("shop_id", shop_id);
    const queryString = query.toString() ? `?${query.toString()}` : "";
    return request<Order>(`/api/orders/${id}${queryString}`);
  },

  async getInventory(shop_id?: string): Promise<InventoryItem[]> {
    const query = new URLSearchParams();
    if (shop_id) query.set("shop_id", shop_id);
    const queryString = query.toString() ? `?${query.toString()}` : "";
    return request<InventoryItem[]>(`/api/inventory${queryString}`);
  },

  async approveOrder(
    order_id: string,
    payload: { reviewer_id: string }
  ): Promise<ManualActionResponse> {
    return request<ManualActionResponse>(`/api/verification/approve/${order_id}`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  async rejectOrder(
    order_id: string,
    payload: { reviewer_id: string; reason: string }
  ): Promise<ManualActionResponse> {
    return request<ManualActionResponse>(`/api/verification/reject/${order_id}`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },
};
