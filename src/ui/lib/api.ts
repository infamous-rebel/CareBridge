import { z } from "zod";

/* -------------------------------------------------------------------------- */
/*  Zod schemas — mirror src/api/schemas.py shapes                             */
/* -------------------------------------------------------------------------- */

export const TokenResponseSchema = z.object({
  access_token: z.string(),
  refresh_token: z.string(),
  token_type: z.literal("bearer"),
});
export type TokenResponse = z.infer<typeof TokenResponseSchema>;

export const UserOutSchema = z.object({
  user_id: z.string(),
  email: z.string().email(),
  role: z.enum(["caregiver_primary", "caregiver_secondary", "viewer"]),
  full_name: z.string().nullable().optional(),
  care_recipient_id: z.string().nullable().optional(),
});
export type UserOut = z.infer<typeof UserOutSchema>;

export const AuditEventSchema = z.object({
  event_id: z.string(),
  timestamp: z.string(),
  actor: z.enum([
    "supervisor",
    "medication",
    "appointment",
    "logistics",
    "communication",
    "human",
  ]),
  action_type: z.string(),
  care_recipient_id: z.string(),
  rationale: z.string(),
  outcome: z.enum(["success", "failure", "pending", "escalated"]),
  correlation_id: z.string(),
  authorization_ref: z.string().nullable().optional(),
});
export type AuditEvent = z.infer<typeof AuditEventSchema>;

export const StatusSummarySchema = z.object({
  care_recipient_id: z.string(),
  summary_text: z.string(),
  recent_events: z.array(AuditEventSchema),
  pending_actions: z.array(z.any()),
});
export type StatusSummary = z.infer<typeof StatusSummarySchema>;

export const PendingActionSchema = z.object({
  action_id: z.string(),
  action_type: z.string(),
  care_recipient_id: z.string(),
  rationale: z.string(),
  requested_at: z.string(),
  status: z.enum(["pending", "approved", "rejected"]),
  authorization_ref: z.string().nullable().optional(),
});
export type PendingAction = z.infer<typeof PendingActionSchema>;

export const ActionResponseSchema = z.object({
  status: z.enum(["ok", "degraded"]),
  detail: z.string().nullable().optional(),
  action_id: z.string().nullable().optional(),
  correlation_id: z.string().nullable().optional(),
  acknowledged_at: z.string().nullable().optional(),
});
export type ActionResponse = z.infer<typeof ActionResponseSchema>;

export const QueryResponseSchema = z.object({
  care_recipient_id: z.string(),
  question: z.string(),
  answer: z.string(),
  status: z.enum(["ok", "degraded"]),
});
export type QueryResponse = z.infer<typeof QueryResponseSchema>;

export const MedicationSchema = z.object({
  medication_id: z.string(),
  name: z.string(),
  dosage: z.string(),
  frequency: z.string(),
  refill_threshold: z.number(),
  pharmacy_id: z.string(),
  care_recipient_id: z.string(),
  days_remaining: z.number().optional(),
});
export type Medication = z.infer<typeof MedicationSchema>;

export const AppointmentSchema = z.object({
  appointment_id: z.string(),
  provider_name: z.string(),
  specialty: z.string(),
  datetime: z.string(),
  location: z.string(),
  prep_required: z.array(z.string()),
  transportation_needed: z.boolean(),
  care_recipient_id: z.string(),
});
export type Appointment = z.infer<typeof AppointmentSchema>;

export const DeliveryStatusSchema = z.object({
  delivery_id: z.string(),
  status: z.enum(["pending", "in_transit", "delivered", "failed"]),
  expected_at: z.string().nullable().optional(),
  failure_reason: z.string().nullable().optional(),
});
export type DeliveryStatus = z.infer<typeof DeliveryStatusSchema>;

export const MCPServerInfoSchema = z.object({
  name: z.string(),
  type: z.string(),
  tools: z.array(z.string()),
});
export const MCPServersResponseSchema = z.object({
  count: z.number(),
  servers: z.array(MCPServerInfoSchema),
});
export type MCPServersResponse = z.infer<typeof MCPServersResponseSchema>;

export const HealthResponseSchema = z.object({
  status: z.literal("ok"),
});
export type HealthResponse = z.infer<typeof HealthResponseSchema>;

export const ReadyResponseSchema = z.object({
  status: z.enum(["ok", "degraded"]),
  checks: z.record(z.string(), z.boolean()),
  llm_provider: z.string(),
  llm_available: z.boolean(),
});
export type ReadyResponse = z.infer<typeof ReadyResponseSchema>;

export const PaginatedAuditSchema = z.object({
  items: z.array(AuditEventSchema),
  total: z.number(),
  page: z.number(),
  page_size: z.number(),
  pages: z.number(),
});
export type PaginatedAudit = z.infer<typeof PaginatedAuditSchema>;

export const ErrorResponseSchema = z.object({
  error: z.string(),
  request_id: z.string().nullable().optional(),
});
export type ErrorResponse = z.infer<typeof ErrorResponseSchema>;

/* -------------------------------------------------------------------------- */
/*  Firebase Authentication schemas                                            */
/* -------------------------------------------------------------------------- */

export const FirebaseUserProfileSchema = z.object({
  uid: z.string(),
  email: z.string(),
  name: z.string().nullable().optional(),
  picture: z.string().nullable().optional(),
});
export type FirebaseUserProfile = z.infer<typeof FirebaseUserProfileSchema>;

export const FirebaseTokenResponseSchema = z.object({
  custom_token: z.string(),
  user: UserOutSchema,
  access_token: z.string(),
  refresh_token: z.string(),
  token_type: z.literal("bearer"),
});
export type FirebaseTokenResponse = z.infer<typeof FirebaseTokenResponseSchema>;

export const FirebaseConfigResponseSchema = z.object({
  enabled: z.boolean(),
  project_id: z.string().nullable().optional(),
});
export type FirebaseConfigResponse = z.infer<typeof FirebaseConfigResponseSchema>;

/* -------------------------------------------------------------------------- */
/*  CRUD schemas for medications, appointments, settings                       */
/* -------------------------------------------------------------------------- */

export const MedicationOutSchema = z.object({
  id: z.string(),
  care_recipient_id: z.string(),
  name: z.string(),
  dosage: z.string(),
  frequency: z.string(),
  refill_threshold: z.number(),
  pharmacy_id: z.string().nullable().optional(),
  notes: z.string().nullable().optional(),
  active: z.number().optional(),
  created_at: z.string(),
  updated_at: z.string().nullable().optional(),
});
export type MedicationOut = z.infer<typeof MedicationOutSchema>;

export const MedicationCreateSchema = z.object({
  name: z.string().min(1).max(200),
  dosage: z.string().min(1).max(100),
  frequency: z.string().min(1).max(100),
  refill_threshold: z.number().int().min(1).max(30).default(5),
  pharmacy_id: z.string().nullable().optional(),
  notes: z.string().nullable().optional(),
});
export type MedicationCreate = z.infer<typeof MedicationCreateSchema>;

export const AppointmentOutSchema = z.object({
  id: z.string(),
  care_recipient_id: z.string(),
  provider_name: z.string(),
  specialty: z.string().nullable().optional(),
  appointment_at: z.string(),
  location: z.string().nullable().optional(),
  prep_required: z.array(z.string()),
  transportation_needed: z.boolean(),
  notes: z.string().nullable().optional(),
  status: z.string(),
  created_at: z.string(),
});
export type AppointmentOut = z.infer<typeof AppointmentOutSchema>;

export const AppointmentCreateSchema = z.object({
  provider_name: z.string().min(1).max(200),
  specialty: z.string().nullable().optional(),
  appointment_at: z.string().min(1),
  location: z.string().nullable().optional(),
  prep_required: z.array(z.string()).max(10).default([]),
  transportation_needed: z.boolean().default(false),
  notes: z.string().nullable().optional(),
});
export type AppointmentCreate = z.infer<typeof AppointmentCreateSchema>;

export const SettingsOutSchema = z.object({
  user_id: z.string(),
  notification_prefs: z.record(z.boolean()),
  escalation_order: z.array(z.any()),
  timezone: z.string(),
  language: z.string(),
  quiet_hours_start: z.string().nullable().optional(),
  quiet_hours_end: z.string().nullable().optional(),
  updated_at: z.string().nullable().optional(),
});
export type SettingsOut = z.infer<typeof SettingsOutSchema>;

export const SettingsUpdateSchema = z.object({
  notification_prefs: z.record(z.boolean()).optional(),
  escalation_order: z.array(z.any()).optional(),
  timezone: z.string().optional(),
  language: z.string().optional(),
  quiet_hours_start: z.string().nullable().optional(),
  quiet_hours_end: z.string().nullable().optional(),
});
export type SettingsUpdate = z.infer<typeof SettingsUpdateSchema>;

/* -------------------------------------------------------------------------- */
/*  API client                                                                 */
/* -------------------------------------------------------------------------- */

const BASE_URL =
  typeof window !== "undefined" && window.location.hostname !== "localhost"
    ? "" // production: same-origin
    : ""; // dev: rewrites handle /api -> backend

interface ApiError {
  error: string;
  request_id: string | null;
  status: number;
}

class ApiClient {
  private accessToken: string | null = null;
  private refreshing: Promise<TokenResponse | null> | null = null;

  setAccessToken(token: string | null) {
    this.accessToken = token;
  }

  getAccessToken(): string | null {
    return this.accessToken;
  }

  clearTokens() {
    this.accessToken = null;
    // The refresh token is httpOnly, so we cannot clear it from JS.
    // The backend handles clearing on logout.
  }

  private async request<T>(
    method: string,
    path: string,
    body?: unknown,
    schema?: z.ZodType<T>,
  ): Promise<T> {
    const url = `${BASE_URL}/api${path}`;
    const headers: Record<string, string> = {
      "Content-Type": "application/json",
    };
    if (this.accessToken) {
      headers["Authorization"] = `Bearer ${this.accessToken}`;
    }

    let res: Response;
    try {
      res = await fetch(url, {
        method,
        headers,
        body: body ? JSON.stringify(body) : undefined,
      });
    } catch {
      throw {
        error: "Network error — is the backend running?",
        request_id: null,
        status: 0,
      } satisfies ApiError;
    }

    if (res.status === 401 && !path.startsWith("/auth/")) {
      // Attempt one refresh
      const refreshed = await this.tryRefresh();
      if (refreshed) {
        headers["Authorization"] = `Bearer ${refreshed.access_token}`;
        res = await fetch(url, {
          method,
          headers,
          body: body ? JSON.stringify(body) : undefined,
        });
      }
    }

    if (res.status === 401) {
      // Redirect to login on persistent auth failure
      if (typeof window !== "undefined") {
        window.location.href = "/login";
      }
      throw {
        error: "Session expired",
        request_id: null,
        status: 401,
      } satisfies ApiError;
    }

    const text = await res.text();
    let data: unknown;
    try {
      data = text ? JSON.parse(text) : null;
    } catch {
      data = text;
    }

    if (!res.ok) {
      const parsed = ErrorResponseSchema.safeParse(data);
      throw {
        error: parsed.success ? parsed.data.error : String(data ?? res.statusText),
        request_id: parsed.success ? parsed.data.request_id ?? null : null,
        status: res.status,
      } satisfies ApiError;
    }

    if (schema) {
      const result = schema.safeParse(data);
      if (!result.success) {
        throw {
          error: `Response validation failed: ${result.error.message}`,
          request_id: null,
          status: res.status,
        } satisfies ApiError;
      }
      return result.data;
    }
    return data as T;
  }

  private async tryRefresh(): Promise<TokenResponse | null> {
    if (this.refreshing) return this.refreshing;
    this.refreshing = this.request<TokenResponse>(
      "POST",
      "/auth/refresh",
      {},
      TokenResponseSchema,
    ).catch(() => null);
    const result = await this.refreshing;
    this.refreshing = null;
    if (result) {
      this.accessToken = result.access_token;
    }
    return result;
  }

  /* -- Auth -- */
  async login(email: string, password: string): Promise<TokenResponse> {
    return this.request("POST", "/auth/login", { email, password }, TokenResponseSchema);
  }

  async refresh(refreshToken: string): Promise<TokenResponse> {
    return this.request(
      "POST",
      "/auth/refresh",
      { refresh_token: refreshToken },
      TokenResponseSchema,
    );
  }

  async getMe(): Promise<UserOut> {
    return this.request("GET", "/auth/me", undefined, UserOutSchema);
  }

  /* -- Status -- */
  async getStatus(careRecipientId: string): Promise<StatusSummary> {
    return this.request(
      "GET",
      `/status/${encodeURIComponent(careRecipientId)}`,
      undefined,
      StatusSummarySchema,
    );
  }

  /* -- Alerts -- */
  async getAlerts(careRecipientId?: string): Promise<AuditEvent[]> {
    const params = careRecipientId
      ? `?care_recipient_id=${encodeURIComponent(careRecipientId)}`
      : "";
    return this.request("GET", `/alerts${params}`, undefined, z.array(AuditEventSchema));
  }

  async ackAlert(alertId: string, note?: string): Promise<ActionResponse> {
    return this.request(
      "POST",
      `/alerts/${encodeURIComponent(alertId)}/ack`,
      { note: note ?? null },
      ActionResponseSchema,
    );
  }

  /* -- Approvals -- */
  async getApprovals(careRecipientId?: string): Promise<PendingAction[]> {
    const params = careRecipientId
      ? `?care_recipient_id=${encodeURIComponent(careRecipientId)}`
      : "";
    return this.request(
      "GET",
      `/approvals${params}`,
      undefined,
      z.array(PendingActionSchema),
    );
  }

  async approveAction(actionId: string): Promise<ActionResponse> {
    return this.request(
      "POST",
      `/approvals/${encodeURIComponent(actionId)}/approve`,
      {},
      ActionResponseSchema,
    );
  }

  async rejectAction(actionId: string): Promise<ActionResponse> {
    return this.request(
      "POST",
      `/approvals/${encodeURIComponent(actionId)}/reject`,
      {},
      ActionResponseSchema,
    );
  }

  /* -- Audit -- */
  async getAudit(
    page = 1,
    filters: {
      actor?: string;
      outcome?: string;
      care_recipient_id?: string;
    } = {},
  ): Promise<PaginatedAudit> {
    const params = new URLSearchParams({
      page: String(page),
      page_size: "50",
    });
    if (filters.actor) params.set("actor", filters.actor);
    if (filters.outcome) params.set("outcome", filters.outcome);
    if (filters.care_recipient_id)
      params.set("care_recipient_id", filters.care_recipient_id);
    return this.request(
      "GET",
      `/audit?${params.toString()}`,
      undefined,
      PaginatedAuditSchema,
    );
  }

  /* -- Query -- */
  async query(
    careRecipientId: string,
    question: string,
  ): Promise<QueryResponse> {
    return this.request(
      "POST",
      "/query",
      { care_recipient_id: careRecipientId, question },
      QueryResponseSchema,
    );
  }

  /* -- Medications -- */
  async getMedications(careRecipientId: string): Promise<Medication[]> {
    return this.request(
      "GET",
      `/medications/${encodeURIComponent(careRecipientId)}`,
      undefined,
      z.array(MedicationSchema),
    );
  }

  /* -- Appointments -- */
  async getAppointments(
    careRecipientId: string,
    horizonDays = 30,
  ): Promise<Appointment[]> {
    return this.request(
      "GET",
      `/appointments/${encodeURIComponent(careRecipientId)}?horizon_days=${horizonDays}`,
      undefined,
      z.array(AppointmentSchema),
    );
  }

  /* -- Deliveries -- */
  async getDeliveries(careRecipientId: string): Promise<DeliveryStatus[]> {
    return this.request(
      "GET",
      `/deliveries/${encodeURIComponent(careRecipientId)}`,
      undefined,
      z.array(DeliveryStatusSchema),
    );
  }

  /* -- MCP -- */
  async getMCPServers(): Promise<MCPServersResponse> {
    return this.request(
      "GET",
      "/mcp/servers",
      undefined,
      MCPServersResponseSchema,
    );
  }

  /* -- Health -- */
  async getHealth(): Promise<HealthResponse> {
    return this.request("GET", "/health", undefined, HealthResponseSchema);
  }

  async getReady(): Promise<ReadyResponse> {
    return this.request("GET", "/ready", undefined, ReadyResponseSchema);
  }

  /* -- Firebase Authentication -- */
  async exchangeFirebaseToken(
    idToken: string
  ): Promise<FirebaseTokenResponse> {
    return this.request(
      "POST",
      "/auth/firebase/exchange",
      { id_token: idToken },
      FirebaseTokenResponseSchema,
    );
  }

  async getFirebaseConfig(): Promise<FirebaseConfigResponse> {
    return this.request(
      "GET",
      "/auth/firebase/config",
      undefined,
      FirebaseConfigResponseSchema,
    );
  }

  /** Replace the internal session state with tokens from a Firebase exchange. */
  setTokens(access: string, refresh?: string) {
    this.accessToken = access;
    // refresh token is stored by the caller (sessionStorage) for now.
    void refresh;
  }

  /* -- CRUD: Medications -- */
  async listMedications(): Promise<MedicationOut[]> {
    return this.request(
      "GET",
      "/care-recipients/me/medications",
      undefined,
      z.array(MedicationOutSchema),
    );
  }

  async createMedication(data: MedicationCreate): Promise<MedicationOut> {
    return this.request(
      "POST",
      "/care-recipients/me/medications",
      data,
      MedicationOutSchema,
    );
  }

  async updateMedication(id: string, data: Partial<MedicationCreate>): Promise<MedicationOut> {
    return this.request(
      "PUT",
      `/care-recipients/me/medications/${encodeURIComponent(id)}`,
      data,
      MedicationOutSchema,
    );
  }

  async deleteMedication(id: string): Promise<void> {
    return this.request(
      "DELETE",
      `/care-recipients/me/medications/${encodeURIComponent(id)}`,
      undefined,
      undefined,
    );
  }

  /* -- CRUD: Appointments -- */
  async listAppointments(): Promise<AppointmentOut[]> {
    return this.request(
      "GET",
      "/care-recipients/me/appointments",
      undefined,
      z.array(AppointmentOutSchema),
    );
  }

  async createAppointment(data: AppointmentCreate): Promise<AppointmentOut> {
    return this.request(
      "POST",
      "/care-recipients/me/appointments",
      data,
      AppointmentOutSchema,
    );
  }

  async updateAppointment(id: string, data: Partial<AppointmentCreate>): Promise<AppointmentOut> {
    return this.request(
      "PUT",
      `/care-recipients/me/appointments/${encodeURIComponent(id)}`,
      data,
      AppointmentOutSchema,
    );
  }

  async cancelAppointment(id: string): Promise<AppointmentOut> {
    return this.request(
      "POST",
      `/care-recipients/me/appointments/${encodeURIComponent(id)}/cancel`,
      {},
      AppointmentOutSchema,
    );
  }

  /* -- CRUD: Settings -- */
  async getSettings(): Promise<SettingsOut> {
    return this.request(
      "GET",
      "/settings/me",
      undefined,
      SettingsOutSchema,
    );
  }

  async updateSettings(data: SettingsUpdate): Promise<SettingsOut> {
    return this.request(
      "PUT",
      "/settings/me",
      data,
      SettingsOutSchema,
    );
  }
}

export const api = new ApiClient();
export type { ApiError };
