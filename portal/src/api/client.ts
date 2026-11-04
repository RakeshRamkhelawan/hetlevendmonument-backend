import type {
  FoundationContentListResponse,
  FoundationContentListItem,
  FoundationContentDetail,
  GeoFeatureCollection,
  CuratieQueueResponse,
  CurationAnalyticsResponse,
  EduSessionContext,
  TenantPublicInfo,
  CreateEduCodeRequest,
  EduCodeCreateResponse,
  EduCodeListResponse,
  DonationCheckoutRequest,
  DonationCheckoutResponse,
  DonationStats,
  PortalSettingsResponse,
  PortalSettingsUpdateRequest,
  ContactSubmissionRequest,
  ContactSubmissionResponse,
  TakedownListResponse,
  TakedownDetailResponse,
  TakedownResolveRequest,
  TakedownResolveResponse,
  FoundationMediaResponse,
  BulkModerationResponse,
  ArchiveExportItem,
  ArchiveExportListResponse,
  AntwoordItem,
  DocentAanvraag,
  DocentAanvraagItem,
  DocentIk,
  DocentItem,
  KlasItem,
  KlasMetCode,
  LeerlingAntwoord,
  LesmateriaalDetail,
  LesmateriaalItem,
  Niveau,
} from '../types';

export type { FoundationContentListItem, FoundationContentDetail, FoundationContentListResponse };

function normalizeItem(raw: any): FoundationContentListItem {
  return {
    ...raw,
    title: raw.title || raw.title_nl || 'Naamloos erfgoedstuk',
    summary: raw.summary || raw.description_nl || raw.description || null,
    creator_name: raw.is_anonymous ? null : (raw.creator_name || raw.author_name || null),
    location_name: raw.location_name || null,
    content_type: raw.content_type || raw.type || 'story',
    status: raw.status || 'pending',
    visibility: raw.visibility || raw.privacy || 'public',
    created_at: raw.created_at || new Date().toISOString(),
    updated_at: raw.updated_at || raw.created_at || new Date().toISOString(),
  };
}

function normalizeDetail(raw: any): FoundationContentDetail {
  const item = normalizeItem(raw);
  return {
    ...item,
    body: raw.body || raw.body_nl || raw.description_nl || '',
    description: raw.description || raw.description_nl || '',
    rights_confirmed: !!raw.rights_confirmed,
    external_url: raw.external_url || null,
    license: raw.license || 'CC-BY-4.0',
    metadata: raw.metadata || raw.metadata_ || null,
    rejection_reason: raw.rejection_reason || null,
    ai_tagging_failed: !!raw.ai_tagging_failed,
    moderation_score: raw.moderation_score ?? null,
    bestanden: (raw.bestanden || []).map((b: any) => ({
      id: b.id,
      volgorde: b.volgorde,
      file_mime: b.file_mime,
      file_size_bytes: b.file_size_bytes,
    })),
    tags: (raw.tags || []).map((t: any) => ({
      id: t.id,
      tag: t.tag || t.value || '',
      tag_type: t.tag_type || 'THEME',
      confidence: t.confidence ?? 1.0,
    })),
  };
}

export class ApiClient {
  private baseUrl: string;
  private tenantSlug: string;
  private tenantPublicInfo: TenantPublicInfo | null = null;
  private resolveTenantPromise: Promise<TenantPublicInfo> | null = null;

  constructor(tenantSlug = 'default', baseUrl = '/api/v1') {
    this.tenantSlug = tenantSlug;
    this.baseUrl = baseUrl;
  }

  public setTenantSlug(slug: string) {
    this.tenantSlug = slug;
  }

  public getTenantSlug(): string {
    return this.tenantSlug;
  }

  public getTenantPublicInfo(): TenantPublicInfo | null {
    return this.tenantPublicInfo;
  }

  public setTenantPublicInfo(info: TenantPublicInfo) {
    this.tenantPublicInfo = info;
    this.setTenantSlug(info.slug);
  }

  public resetTenantCache(): void {
    this.tenantPublicInfo = null;
    this.resolveTenantPromise = null;
  }

  public async resolveCurrentTenant(options?: {
    host?: string;
    slug?: string;
    domain?: string;
    forceRefresh?: boolean;
  }): Promise<TenantPublicInfo> {
    if (!options?.forceRefresh) {
      if (this.tenantPublicInfo) {
        const slugMatch = !options?.slug || this.tenantPublicInfo.slug === options.slug;
        const domainMatch = !options?.domain || this.tenantPublicInfo.domain === options.domain;
        if (slugMatch && domainMatch) {
          return this.tenantPublicInfo;
        }
      }
      if (this.resolveTenantPromise) {
        return this.resolveTenantPromise;
      }
    }

    const fetchPromise = (async () => {
      try {
        const params = new URLSearchParams();
        if (options?.slug) {
          params.set('slug', options.slug);
        }
        if (options?.domain) {
          params.set('domain', options.domain);
        }
        const query = params.toString() ? `?${params.toString()}` : '';
        const url = `${this.baseUrl}/foundation/tenant/resolve${query}`;

        const headers: Record<string, string> = {
          Accept: 'application/json',
        };

        if (options?.host) {
          headers['x-tenant-domain'] = options.host;
        }

        const response = await fetch(url, {
          method: 'GET',
          headers,
        });

        if (!response.ok) {
          let errorDetail = response.statusText;
          try {
            const errorJson = await response.json();
            errorDetail = errorJson.detail || errorJson.message || JSON.stringify(errorJson);
          } catch {
            // use statusText
          }
          throw new Error(`Tenant resolution failed (${response.status}): ${errorDetail}`);
        }

        const data: TenantPublicInfo = await response.json();
        this.setTenantPublicInfo(data);
        return data;
      } finally {
        this.resolveTenantPromise = null;
      }
    })();

    this.resolveTenantPromise = fetchPromise;
    return fetchPromise;
  }


  public getAuthToken(): string | null {
    return localStorage.getItem('portal_token');
  }

  public setAuthToken(token: string) {
    localStorage.setItem('portal_token', token);
  }

  public clearAuthToken() {
    localStorage.removeItem('portal_token');
  }

  private async request<T>(path: string, options: RequestInit = {}): Promise<T> {
    const url = `${this.baseUrl}/${this.tenantSlug}/foundation${path}`;
    const headers: Record<string, string> = {
      ...(options.headers as Record<string, string>),
    };

    const token = this.getAuthToken();
    if (token && !headers['Authorization']) {
      headers['Authorization'] = `Bearer ${token}`;
    }

    if (!(options.body instanceof FormData) && !headers['Content-Type']) {
      headers['Content-Type'] = 'application/json';
    }

    const response = await fetch(url, {
      ...options,
      headers,
    });

    if (!response.ok) {
      if (response.status === 401) {
        let isExpiredOrInvalid = false;
        try {
          const cloned = response.clone();
          const errorJson = await cloned.json();
          const detail = typeof errorJson.detail === 'string' ? errorJson.detail.toLowerCase() : '';
          isExpiredOrInvalid =
            detail.includes('expired') ||
            detail.includes('invalid or expired') ||
            detail.includes('credentials') ||
            detail.includes('signature');
        } catch {
          // ignore
        }
        if (!path.startsWith('/edu/') && (isExpiredOrInvalid || path.includes('/auth/magic-link'))) {
          this.clearAuthToken();
          if (typeof window !== 'undefined') {
            window.dispatchEvent(new CustomEvent('auth:unauthorized'));
          }
        }
      }
      let errorDetail = response.statusText;
      try {
        const errorJson = await response.json();
        if (typeof errorJson.detail === 'string') {
          errorDetail = errorJson.detail;
        } else if (Array.isArray(errorJson.detail)) {
          errorDetail = errorJson.detail
            .map((d: any) => d.msg || (typeof d === 'string' ? d : JSON.stringify(d)))
            .join(', ');
        } else if (errorJson.message) {
          errorDetail = errorJson.message;
        } else {
          errorDetail = JSON.stringify(errorJson);
        }
      } catch {
        // Fallback to status text
      }
      throw new Error(`API Error [${response.status}]: ${errorDetail}`);
    }

    return response.json();
  }

  // Content public endpoints
  async getContentList(params?: {
    page?: number;
    page_size?: number;
    category?: string;
  }): Promise<FoundationContentListResponse> {
    const query = new URLSearchParams();
    if (params?.page) query.append('page', params.page.toString());
    if (params?.page_size) query.append('page_size', params.page_size.toString());
    if (params?.category) query.append('category', params.category);

    const queryString = query.toString() ? `?${query.toString()}` : '';
    const res = await this.request<any>(`/content${queryString}`);
    return {
      items: (res.items || []).map(normalizeItem),
      total: res.total || 0,
      page: res.page || 1,
      page_size: res.page_size || 12,
    };
  }

  async getContentDetail(id: number | string): Promise<FoundationContentDetail> {
    const res = await this.request<any>(`/content/${id}`);
    return normalizeDetail(res);
  }

  async getMySubmissions(params?: {
    page?: number;
    page_size?: number;
  }): Promise<FoundationContentListResponse> {
    const query = new URLSearchParams();
    if (params?.page) query.append('page', params.page.toString());
    if (params?.page_size) query.append('page_size', params.page_size.toString());
    const queryString = query.toString() ? `?${query.toString()}` : '';
    const res = await this.request<any>(`/content/my-submissions${queryString}`);
    return {
      items: (res.items || []).map(normalizeItem),
      total: res.total || 0,
      page: res.page || 1,
      page_size: res.page_size || 20,
    };
  }

  // Geo map endpoint
  async getMapBbox(bounds: {
    minLng: number;
    minLat: number;
    maxLng: number;
    maxLat: number;
  }): Promise<GeoFeatureCollection> {
    let { minLng, minLat, maxLng, maxLat } = bounds;
    // Backend enforces anti-scrape limit of max 2.0 degrees per axis (BE-EP-037)
    // Clamp to 1.95 degrees around center point if zoomed out too far
    if (maxLng - minLng > 2.0) {
      const midLng = (minLng + maxLng) / 2;
      minLng = Math.max(-180, midLng - 0.95);
      maxLng = Math.min(180, midLng + 0.95);
    }
    if (maxLat - minLat > 2.0) {
      const midLat = (minLat + maxLat) / 2;
      minLat = Math.max(-90, midLat - 0.95);
      maxLat = Math.min(90, midLat + 0.95);
    }

    const query = new URLSearchParams({
      sw_lat: minLat.toFixed(4),
      sw_lng: minLng.toFixed(4),
      ne_lat: maxLat.toFixed(4),
      ne_lng: maxLng.toFixed(4),
      min_lng: minLng.toFixed(4),
      min_lat: minLat.toFixed(4),
      max_lng: maxLng.toFixed(4),
      max_lat: maxLat.toFixed(4),
    });
    const res = await this.request<GeoFeatureCollection>(`/map/bbox?${query.toString()}`);
    // De backend levert title_nl (map.py, O8-set); de kaartlijst leest properties.title.
    return {
      ...res,
      features: (res.features || []).map((f) => {
        const p = f.properties as GeoFeatureCollection['features'][number]['properties'] & {
          title_nl?: string;
        };
        return { ...f, properties: { ...p, title: p.title || p.title_nl || 'Naamloos erfgoedstuk' } };
      }),
    };
  }

  // Story submission & upload
  async submitContent(payload: {
    title: string;
    category?: string;
    body: string;
    author_name?: string;
    author_email?: string;
    is_anonymous?: boolean;
    location_name?: string;
    latitude?: number;
    longitude?: number;
    file_url?: string;
    media_type?: string;
    rights_confirmed?: boolean;
  }): Promise<{ id: string }> {
    const res = await this.request<{ id: number }>('/content', {
      method: 'POST',
      body: JSON.stringify({
        title_nl: payload.title,
        type: payload.media_type === 'audio' ? 'audio' : 'story',
        body_nl: payload.body,
        description_nl: payload.body.slice(0, 200),
        creator_name: payload.author_name || null,
        is_anonymous: !!payload.is_anonymous,
        lat: payload.latitude,
        lng: payload.longitude,
        location_name: payload.location_name,
        category: payload.category,
        rights_confirmed: true,
        license: 'CC-BY-4.0',
      }),
    });
    return { id: res.id.toString() };
  }

  async createContent(payload: any): Promise<FoundationContentDetail> {
    const res = await this.request<any>('/content', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
    return normalizeDetail(res);
  }

  async uploadMedia(
    contentId: number | string,
    file: File,
    opties?: { extra?: boolean }
  ): Promise<{ file_url: string; bestand_id?: number | null }> {
    const formData = new FormData();
    formData.append('file', file);
    // BE-EP-057: extra=true voegt een bestand toe; zonder hoofdbestand wordt het het hoofdbestand.
    const extra = opties?.extra ? '?extra=true' : '';
    return this.request<{ file_url: string; bestand_id?: number | null }>(`/content/${contentId}/upload${extra}`, {
      method: 'POST',
      body: formData,
    });
  }

  /** URL van een extra bestand bij een verhaal (BE-EP-057); zelfde opties als getMediaUrl. */
  getBestandMediaUrl(
    contentId: number | string,
    bestandId: number | string,
    options?: { download?: boolean; stream?: boolean }
  ): string {
    const params = new URLSearchParams();
    if (options?.stream) {
      params.set('stream', 'true');
    } else {
      params.set('redirect', 'true');
    }
    if (options?.download) {
      params.set('download', 'true');
    }
    return `${this.baseUrl}/${this.tenantSlug}/foundation/content/${contentId}/bestanden/${bestandId}/media?${params.toString()}`;
  }

  async getBestandMediaInfo(contentId: number | string, bestandId: number | string): Promise<FoundationMediaResponse> {
    return this.request<FoundationMediaResponse>(`/content/${contentId}/bestanden/${bestandId}/media`);
  }

  getMediaUrl(contentId: number | string, options?: { download?: boolean; stream?: boolean }): string {
    const params = new URLSearchParams();
    if (options?.stream) {
      params.set('stream', 'true');
    } else {
      params.set('redirect', 'true');
    }
    if (options?.download) {
      params.set('download', 'true');
    }
    return `${this.baseUrl}/${this.tenantSlug}/foundation/content/${contentId}/media?${params.toString()}`;
  }

  async getMediaInfo(contentId: number | string): Promise<FoundationMediaResponse> {
    return this.request<FoundationMediaResponse>(`/content/${contentId}/media`);
  }


  // Auth / Magic link
  async requestMagicLink(
    email: string,
    hcaptchaToken?: string | null,
    opties?: { aanmelden?: boolean }
  ): Promise<{ message: string; dev_magic_link_url?: string; dev_token?: string }> {
    return this.request<{ message: string; dev_magic_link_url?: string; dev_token?: string }>('/auth/magic-link', {
      method: 'POST',
      body: JSON.stringify({
        email,
        ...(hcaptchaToken ? { hcaptcha_token: hcaptchaToken } : {}),
        // BE-EP-056: een onbekend adres krijgt een bezoekersaccount (verteller).
        ...(opties?.aanmelden ? { aanmelden: true } : {}),
      }),
    });
  }

  async verifyMagicLink(token: string): Promise<{ access_token: string; user: { email: string; role: string } }> {
    const res = await this.request<{ access_token: string; user: { email: string; role: string } }>(
      '/auth/magic-link/verify',
      {
        method: 'POST',
        body: JSON.stringify({ token }),
      }
    );
    if (res.access_token) {
      this.setAuthToken(res.access_token);
    }
    return res;
  }

  async loginWithPassword(
    username: string,
    password: string
  ): Promise<{ access_token: string; token_type: string; user: { email: string; role: string } }> {
    const res = await this.request<{ access_token: string; token_type: string; user: { email: string; role: string } }>(
      '/auth/login',
      {
        method: 'POST',
        body: JSON.stringify({ username, password }),
      }
    );
    if (res.access_token) {
      this.setAuthToken(res.access_token);
    }
    return res;
  }

  async quickLogin(
    role: 'admin' | 'curator' | 'bezoeker'
  ): Promise<{ access_token: string; token_type: string; user: { email: string; role: string } }> {
    const res = await this.request<{ access_token: string; token_type: string; user: { email: string; role: string } }>(
      '/auth/quick-login',
      {
        method: 'POST',
        body: JSON.stringify({ role }),
      }
    );
    if (res.access_token) {
      this.setAuthToken(res.access_token);
    }
    return res;
  }

  // Newsletter
  async subscribeNewsletter(
    email: string,
    name?: string,
    preferences?: string[],
    hcaptchaToken?: string | null
  ): Promise<{ message: string }> {
    return this.request<{ message: string }>('/newsletter/subscribe', {
      method: 'POST',
      body: JSON.stringify({
        email,
        ...(name ? { name } : {}),
        ...(preferences ? { preferences } : {}),
        ...(hcaptchaToken ? { hcaptcha_token: hcaptchaToken } : {}),
      }),
    });
  }

  async confirmNewsletter(email: string, token: string): Promise<{ message: string }> {
    return this.request<{ message: string }>('/newsletter/confirm', {
      method: 'POST',
      body: JSON.stringify({ email, token }),
    });
  }

  async unsubscribeNewsletter(email: string, token: string): Promise<{ message: string }> {
    return this.request<{ message: string }>('/newsletter/unsubscribe', {
      method: 'POST',
      body: JSON.stringify({ email, token }),
    });
  }

  // Notice & Takedown
  async submitTakedown(
    payload: {
      content_id: number;
      reason: string;
      contact_email: string;
      [key: string]: unknown;
    },
    hcaptchaToken?: string | null
  ): Promise<{ id: number; message: string }> {
    return this.request<{ id: number; message: string }>('/takedown', {
      method: 'POST',
      body: JSON.stringify({
        ...payload,
        ...(hcaptchaToken ? { hcaptcha_token: hcaptchaToken } : {}),
      }),
    });
  }


  // Educational Portal
  async validateEduAccess(code: string): Promise<{ status: string; role: 'teacher' | 'student' }> {
    const res = await this.request<{ role: string; expires_at: string | null }>('/edu/session', {
      method: 'POST',
      body: JSON.stringify({ code }),
    });
    return {
      status: 'valid',
      role: (res.role as 'teacher' | 'student') || 'student',
    };
  }

  async createEduCode(data: CreateEduCodeRequest): Promise<EduCodeCreateResponse> {
    return this.request<EduCodeCreateResponse>('/edu/codes', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async getEduCodes(params?: { teacher_email?: string; active_only?: boolean }): Promise<EduCodeListResponse> {
    const query = new URLSearchParams();
    if (params?.teacher_email) query.set('teacher_email', params.teacher_email);
    if (params?.active_only !== undefined) query.set('active_only', String(params.active_only));
    const qs = query.toString() ? `?${query.toString()}` : '';
    return this.request<EduCodeListResponse>(`/edu/codes${qs}`);
  }

  async revokeEduCode(id: number): Promise<void> {
    return this.request<void>(`/edu/codes/${id}`, {
      method: 'DELETE',
    });
  }

  // Docentenomgeving (BE-EP-055)
  async vraagDocentaccountAan(data: DocentAanvraag): Promise<{ message: string }> {
    return this.request<{ message: string }>('/docent/aanvraag', { method: 'POST', body: JSON.stringify(data) });
  }

  async getDocentIk(): Promise<DocentIk> {
    return this.request<DocentIk>('/docent/ik');
  }

  async getLesmateriaal(): Promise<LesmateriaalItem[]> {
    return this.request<LesmateriaalItem[]>('/docent/lesmateriaal');
  }

  async getLesmateriaalDetail(id: number | string): Promise<FoundationContentDetail> {
    const res = await this.request<LesmateriaalDetail>(`/docent/lesmateriaal/${id}`);
    return normalizeDetail({
      ...res,
      title_nl: res.title,
      description_nl: res.description,
      body_nl: res.body,
      status: 'approved',
      visibility: res.type === 'teacher_guide' ? 'public' : 'edu',
      category: 'educatie',
      content_type: res.type,
    });
  }

  /** De PDF als Blob; met het docenttoken in de header, dus geen gewone link. */
  async downloadLesPdf(id: number): Promise<Blob> {
    const url = `${this.baseUrl}/${this.tenantSlug}/foundation/docent/lesmateriaal/${id}/pdf`;
    const token = this.getAuthToken();
    const response = await fetch(url, { headers: token ? { Authorization: `Bearer ${token}` } : {} });
    if (!response.ok) throw new Error(`API Error [${response.status}]: PDF niet beschikbaar`);
    return response.blob();
  }

  async getKlassen(): Promise<KlasItem[]> {
    return this.request<KlasItem[]>('/docent/klassen');
  }

  async maakKlas(data: { naam: string; niveau: Niveau; geldig_dagen: number; les_ids?: number[] }): Promise<KlasMetCode> {
    return this.request<KlasMetCode>('/docent/klassen', { method: 'POST', body: JSON.stringify(data) });
  }

  async nieuweKlascode(klasId: number, geldigDagen: number): Promise<KlasMetCode> {
    return this.request<KlasMetCode>(`/docent/klassen/${klasId}/nieuwe-code`, {
      method: 'POST',
      body: JSON.stringify({ geldig_dagen: geldigDagen }),
    });
  }

  async trekKlascodeIn(klasId: number): Promise<KlasItem> {
    return this.request<KlasItem>(`/docent/klassen/${klasId}/intrekken`, { method: 'POST' });
  }

  async zetKlaslessen(klasId: number, lesIds: number[]): Promise<KlasItem> {
    return this.request<KlasItem>(`/docent/klassen/${klasId}/lessen`, {
      method: 'PUT',
      body: JSON.stringify({ les_ids: lesIds }),
    });
  }

  async getKlasantwoorden(klasId: number, lesId?: number): Promise<AntwoordItem[]> {
    const qs = lesId ? `?les_id=${lesId}` : '';
    return this.request<AntwoordItem[]>(`/docent/klassen/${klasId}/antwoorden${qs}`);
  }

  async geefFeedback(antwoordId: number, feedback: string): Promise<AntwoordItem> {
    return this.request<AntwoordItem>(`/docent/antwoorden/${antwoordId}/feedback`, {
      method: 'PUT',
      body: JSON.stringify({ feedback }),
    });
  }

  async getMijnAntwoorden(contentId: number | string, token: string): Promise<LeerlingAntwoord> {
    return this.request<LeerlingAntwoord>(`/edu/antwoorden/${contentId}`, { headers: { 'X-Leerling-Token': token } });
  }

  async slaAntwoordenOp(
    contentId: number | string,
    token: string,
    data: { naam: string; antwoorden: Record<string, string> },
  ): Promise<LeerlingAntwoord> {
    return this.request<LeerlingAntwoord>(`/edu/antwoorden/${contentId}`, {
      method: 'PUT',
      headers: { 'X-Leerling-Token': token },
      body: JSON.stringify(data),
    });
  }

  async getDocentaanvragen(status: 'pending' | 'approved' | 'rejected' | 'alle' = 'pending'): Promise<DocentAanvraagItem[]> {
    return this.request<DocentAanvraagItem[]>(`/admin/docenten/aanvragen?status_filter=${status}`);
  }

  async keurDocentaanvraagGoed(id: number): Promise<DocentAanvraagItem> {
    return this.request<DocentAanvraagItem>(`/admin/docenten/aanvragen/${id}/goedkeuren`, { method: 'POST' });
  }

  async wijsDocentaanvraagAf(id: number, reden?: string): Promise<DocentAanvraagItem> {
    return this.request<DocentAanvraagItem>(`/admin/docenten/aanvragen/${id}/afwijzen`, {
      method: 'POST',
      body: JSON.stringify({ reden: reden || null }),
    });
  }

  async getDocenten(): Promise<DocentItem[]> {
    return this.request<DocentItem[]>('/admin/docenten');
  }

  async trekDocentrolIn(id: number): Promise<DocentItem> {
    return this.request<DocentItem>(`/admin/docenten/${id}/intrekken`, { method: 'POST' });
  }

  async getEduSession(): Promise<EduSessionContext> {
    return this.request<EduSessionContext>('/edu/session');
  }

  async getEduContentDetail(id: number | string): Promise<FoundationContentDetail> {
    const res = await this.request<any>(`/edu/content/${id}`);
    return normalizeDetail(res);
  }

  async getEduContent(): Promise<FoundationContentListResponse> {
    const res = await this.request<any>('/edu/content');
    return {
      items: (res.items || []).map(normalizeItem),
      total: res.total || 0,
      page: res.page || 1,
      page_size: res.page_size || 12,
    };
  }

  // Curator & Admin
  async getCuratieQueue(params?: { status?: string; page?: number }): Promise<CuratieQueueResponse> {
    const query = new URLSearchParams();
    if (params?.status) query.append('status', params.status);
    if (params?.page) query.append('page', params.page.toString());
    const qStr = query.toString() ? `?${query.toString()}` : '';
    const res = await this.request<any>(`/admin/curatie/queue${qStr}`);
    return {
      items: (res.items || []).map((raw: any) => ({
        ...raw,
        title: raw.title || raw.title_nl || 'Naamloos erfgoedstuk',
        summary: raw.summary || raw.description_nl || null,
        creator_name: raw.is_anonymous ? null : (raw.creator_name || null),
        tags: (raw.tags || []).map((t: any) => ({
          id: t.id,
          tag: t.tag || t.value || '',
          tag_type: t.tag_type || 'THEME',
          confidence: t.confidence ?? 1.0,
        })),
      })),
      total: res.total || 0,
      page: res.page || 1,
      page_size: res.page_size || 20,
    };
  }

  async approveContent(contentId: number | string): Promise<FoundationContentDetail> {
    const res = await this.request<any>(`/admin/curatie/${contentId}/approve`, {
      method: 'POST',
    });
    return normalizeDetail(res);
  }

  async rejectContent(contentId: number | string, rejectionReason?: string): Promise<FoundationContentDetail> {
    const res = await this.request<any>(`/admin/curatie/${contentId}/reject`, {
      method: 'POST',
      body: JSON.stringify({ rejection_reason: rejectionReason || '' }),
    });
    return normalizeDetail(res);
  }

  async bulkApproveContent(contentIds: number[]): Promise<BulkModerationResponse> {
    return this.request<BulkModerationResponse>('/admin/curatie/bulk-approve', {
      method: 'POST',
      body: JSON.stringify({ content_ids: contentIds }),
    });
  }

  async bulkRejectContent(contentIds: number[], rejectionReason: string): Promise<BulkModerationResponse> {
    return this.request<BulkModerationResponse>('/admin/curatie/bulk-reject', {
      method: 'POST',
      body: JSON.stringify({ content_ids: contentIds, rejection_reason: rejectionReason }),
    });
  }

  async retagContent(contentId: number | string): Promise<{ content_id: number; status: string; message: string }> {
    return this.request<{ content_id: number; status: string; message: string }>(
      `/admin/curatie/${contentId}/re-tag`,
      { method: 'POST' }
    );
  }

  // BagIt-archiefexport (BE-EP-054)
  async createArchiveExport(): Promise<ArchiveExportItem> {
    return this.request<ArchiveExportItem>('/admin/archief/exports', { method: 'POST' });
  }

  async getArchiveExports(params?: { limit?: number; offset?: number }): Promise<ArchiveExportListResponse> {
    const query = new URLSearchParams();
    if (params?.limit !== undefined) query.set('limit', String(params.limit));
    if (params?.offset !== undefined) query.set('offset', String(params.offset));
    const suffix = query.toString() ? `?${query.toString()}` : '';
    return this.request<ArchiveExportListResponse>(`/admin/archief/exports${suffix}`);
  }

  async downloadArchiveExport(id: number): Promise<Blob> {
    const url = `${this.baseUrl}/${this.tenantSlug}/foundation/admin/archief/exports/${id}/download`;
    const headers: Record<string, string> = {};
    const token = this.getAuthToken();
    if (token) headers['Authorization'] = `Bearer ${token}`;
    const response = await fetch(url, { method: 'GET', headers });
    if (!response.ok) {
      throw new Error(`API Error [${response.status}]: archiefpakket kon niet worden gedownload`);
    }
    return response.blob();
  }

  async getCuratieAnalytics(): Promise<CurationAnalyticsResponse> {
    return this.request<CurationAnalyticsResponse>('/admin/curatie/analytics');
  }

  // Notice & Takedown Moderation (BE-EP-051 / FE-CUR-001)
  async getCuratieTakedowns(params?: {
    status?: string;
    page?: number;
    page_size?: number;
  }): Promise<TakedownListResponse> {
    const query = new URLSearchParams();
    if (params?.status) query.append('status', params.status);
    if (params?.page) query.append('page', params.page.toString());
    if (params?.page_size) query.append('page_size', params.page_size.toString());
    const qStr = query.toString() ? `?${query.toString()}` : '';
    return this.request<TakedownListResponse>(`/admin/curatie/takedowns${qStr}`);
  }

  async getCuratieTakedownDetail(id: number): Promise<TakedownDetailResponse> {
    return this.request<TakedownDetailResponse>(`/admin/curatie/takedowns/${id}`);
  }

  async resolveCuratieTakedown(
    id: number,
    data: TakedownResolveRequest
  ): Promise<TakedownResolveResponse> {
    return this.request<TakedownResolveResponse>(`/admin/curatie/takedowns/${id}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    });
  }

  async restoreContent(contentId: number | string): Promise<FoundationContentDetail> {
    const res = await this.request<any>(`/admin/curatie/${contentId}/restore`, {
      method: 'POST',
    });
    return normalizeDetail(res);
  }

  // Donations & Heritage Adoption (BE-EP-046 / FE-PAGE-012)
  async createDonationCheckout(payload: DonationCheckoutRequest): Promise<DonationCheckoutResponse> {
    return this.request<DonationCheckoutResponse>('/donations/checkout', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  }

  async getDonationStats(): Promise<DonationStats> {
    return this.request<DonationStats>('/donations/stats');
  }

  // White-Label Branding & Portal Settings (BE-EP-047 / FE-PAGE-014)
  async getPortalSettings(): Promise<PortalSettingsResponse> {
    return this.request<PortalSettingsResponse>('/settings');
  }

  async updatePortalSettings(payload: PortalSettingsUpdateRequest): Promise<PortalSettingsResponse> {
    return this.request<PortalSettingsResponse>('/admin/settings', {
      method: 'PUT',
      body: JSON.stringify(payload),
    });
  }

  // Contact & Community Support (BE-EP-048 / FE-PAGE-015)
  async submitContactForm(payload: ContactSubmissionRequest): Promise<ContactSubmissionResponse> {
    return this.request<ContactSubmissionResponse>('/contact', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  }
}

export const api = new ApiClient();
