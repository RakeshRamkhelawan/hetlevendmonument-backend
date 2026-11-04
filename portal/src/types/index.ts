export type TagType = 'THEME' | 'LOCATION' | 'PERIOD' | 'SENTIMENT' | 'LANGUAGE';

export interface ContentTagDetail {
  id: number;
  tag: string;
  tag_type: TagType;
  confidence: number;
}

export type ContentType =
  | 'story'
  | 'image'
  | 'audio'
  | 'video'
  | 'document'
  | 'artwork'
  | 'exhibition'
  | 'educational_workbook'
  | 'curriculum_module'
  | 'historical_archive'
  | 'testimonial_video'
  | 'community_reflection';

export type ContentStatus = 'pending' | 'approved' | 'rejected' | 'removed';
export type Visibility = 'public' | 'edu' | 'community';

export interface FoundationContentListItem {
  id: number;
  title: string;
  summary: string | null;
  creator_name: string | null;
  is_anonymous: boolean;
  language: string;
  content_type: ContentType | string;
  status: ContentStatus;
  visibility: Visibility;
  file_url: string | null;
  file_mime: string | null;
  file_size_bytes: number | null;
  lat: number | null;
  lng: number | null;
  location_name: string | null;
  category: string | null;
  target_age_group?: string | null;
  duration_seconds?: number | null;
  created_at: string;
  updated_at: string;
}

/** Een extra bestand bij een verhaal (BE-EP-057). */
export interface FoundationBestand {
  id: number;
  volgorde: number;
  file_mime: string;
  file_size_bytes: number;
}

export interface FoundationContentDetail extends FoundationContentListItem {
  /** Bestanden na het eerste, op volgorde (BE-EP-057). */
  bestanden?: FoundationBestand[];
  body: string | null;
  description: string | null;
  rights_confirmed: boolean;
  external_url: string | null;
  license: string | null;
  metadata: Record<string, unknown> | null;
  rejection_reason: string | null;
  ai_tagging_failed: boolean;
  moderation_score: number | null;
  tags: ContentTagDetail[];
}

export interface FoundationContentListResponse {
  items: FoundationContentListItem[];
  total: number;
  page: number;
  page_size: number;
}

export interface CuratieQueueItem {
  id: number;
  title: string;
  summary: string | null;
  creator_name: string | null;
  is_anonymous: boolean;
  content_type: string;
  status: ContentStatus;
  created_at: string;
  rejection_reason: string | null;
  ai_tagging_failed: boolean;
  moderation_score: number | null;
  tags: ContentTagDetail[];
}

export interface CuratieQueueResponse {
  items: CuratieQueueItem[];
  total: number;
  page: number;
  page_size: number;
}

export interface BulkFailedItem {
  id: number;
  reason: string;
}

export interface BulkModerationResponse {
  total_requested: number;
  processed_count: number;
  success_ids: number[];
  failed_items: BulkFailedItem[];
  message: string;
}

export interface GeoFeature {
  type: 'Feature';
  geometry: {
    type: 'Point';
    coordinates: [number, number]; // [lng, lat]
  };
  properties: {
    id: number;
    title: string;
    summary?: string | null;
    creator_name?: string | null;
    is_anonymous?: boolean;
    content_type?: string;
    file_url?: string | null;
    location_name?: string | null;
    category?: string | null;
    created_at?: string;
  };
}

export interface GeoFeatureCollection {
  type: 'FeatureCollection';
  features: GeoFeature[];
  has_more: boolean;
}

export interface EduSessionContext {
  // De API geeft nu alleen role en expires_at; de andere velden zijn optioneel.
  session_id?: string;
  access_id?: number;
  role: 'teacher' | 'student';
  tenant_id?: number;
  expires_at?: string;
  is_active?: boolean;
}

export interface TenantPublicInfo {
  id: number;
  name: string;
  slug: string;
  domain: string | null;
  is_active: boolean;
}

export interface CreateEduCodeRequest {
  class_name: string;
  teacher_email: string;
  role?: 'student' | 'teacher';
  valid_hours?: number;
}

export interface EduCodeCreateResponse {
  id: number;
  code: string;
  class_name: string;
  teacher_email: string;
  role: string;
  expires_at: string | null;
  created_at: string;
  is_active: boolean;
}

export interface EduCodeItem {
  id: number;
  class_name: string;
  teacher_email: string;
  role: string;
  expires_at: string | null;
  created_at: string;
  is_active: boolean;
}

export interface EduCodeListResponse {
  items: EduCodeItem[];
  total: number;
}

export interface TagDistributionItem {
  tag: string;
  tag_type: string;
  count: number;
  average_confidence: number;
}

export interface NewsletterAnalytics {
  total_subscribers: number;
  verified_subscribers: number;
}

export interface EducationalAnalytics {
  active_codes: number;
  total_codes: number;
}

export interface CurationAnalyticsResponse {
  status_counts: Record<string, number>;
  total_content: number;
  average_moderation_seconds: number | null;
  tag_distribution: TagDistributionItem[];
  newsletter: NewsletterAnalytics;
  education: EducationalAnalytics;
}

export type DonationFrequency = 'one_time' | 'monthly';

export interface DonationCheckoutRequest {
  amount_cents: number;
  frequency: DonationFrequency;
  donor_email: string;
  donor_name?: string;
  is_anonymous: boolean;
  monument_id?: number;
  message?: string;
  hcaptcha_token?: string;
}

export interface DonationCheckoutResponse {
  checkout_url: string;
  session_id: string;
  amount_cents: number;
  frequency: string;
}

export interface DonationHistoryItem {
  id: number;
  amount_cents: number;
  frequency: string;
  donor_name: string | null;
  message: string | null;
  created_at: string;
  is_anonymous: boolean;
}

export interface DonationStats {
  total_raised_cents: number;
  total_donations_count: number;
  monthly_supporters_count: number;
  recent_donations: DonationHistoryItem[];
}

export interface PortalSettingsResponse {
  platform_name_nl: string;
  platform_name_en?: string | null;
  primary_color: string;
  accent_color: string;
  logo_url?: string | null;
  favicon_url?: string | null;
  guidelines_nl?: string | null;
  guidelines_en?: string | null;
  about_nl?: string | null;
  about_en?: string | null;
  contact_email?: string | null;
}

export interface PortalSettingsUpdateRequest {
  platform_name_nl?: string;
  platform_name_en?: string;
  primary_color?: string;
  accent_color?: string;
  logo_url?: string;
  favicon_url?: string;
  guidelines_nl?: string;
  guidelines_en?: string;
  about_nl?: string;
  about_en?: string;
  contact_email?: string;
}

export type ContactCategory = 'algemeen' | 'educatie' | 'donatie' | 'archief' | 'samenwerking';

export interface ContactSubmissionRequest {
  name: string;
  email: string;
  subject: string;
  category?: ContactCategory;
  message: string;
  hcaptcha_token?: string | null;
}

export interface ContactSubmissionResponse {
  reference_id: string;
  status: string;
  message: string;
  created_at: string;
}

export type TakedownStatus = 'pending' | 'approved' | 'rejected' | 'escalated';

export interface TakedownListItem {
  id: number;
  content_id: number;
  content_title?: string | null;
  content_type?: string | null;
  content_status?: string | null;
  requester_name: string;
  requester_email: string;
  legal_basis: string;
  status: TakedownStatus;
  resolution_note?: string | null;
  resolved_at?: string | null;
  created_at: string;
}

export interface TakedownListResponse {
  items: TakedownListItem[];
  total: number;
  page: number;
  page_size: number;
  status_filter?: string | null;
}

export interface TakedownDetailResponse {
  id: number;
  content_id: number;
  content_title?: string | null;
  content_type?: string | null;
  content_status?: string | null;
  content_description?: string | null;
  content_creator_name?: string | null;
  content_file_url?: string | null;
  requester_name: string;
  requester_email: string;
  legal_basis: string;
  status: TakedownStatus;
  resolution_note?: string | null;
  resolved_at?: string | null;
  created_at: string;
}

export interface TakedownResolveRequest {
  status: TakedownStatus;
  resolution_note: string;
  notify_requester?: boolean;
}

export interface TakedownResolveResponse {
  id: number;
  content_id: number;
  status: TakedownStatus;
  content_status: string;
  resolution_note?: string | null;
  resolved_at?: string | null;
  message: string;
}

export interface FoundationMediaResponse {
  url: string;
  mime_type?: string | null;
  file_size_bytes?: number | null;
  expires_in_seconds: number;
}

// BagIt-archiefexport (ADR-029 Cat 4, BE-EP-054)
export interface ArchiveExportItem {
  id: number;
  bag_name: string;
  item_count: number;
  payload_file_count: number;
  size_bytes: number;
  sha256: string;
  trigger: 'schema' | 'handmatig';
  created_at: string;
}

export interface ArchiveExportListResponse {
  items: ArchiveExportItem[];
  total: number;
  limit: number;
  offset: number;
}

// Docentenomgeving (BE-EP-055)
export type Niveau = 'groep-7-8' | 'onderbouw-vo';

export interface DocentIk {
  email: string;
  display_name: string | null;
  role: string;
  is_docent: boolean;
  aanvraag_status: 'pending' | 'approved' | 'rejected' | null;
}

export interface DocentAanvraag {
  name: string;
  email: string;
  school: string;
  function?: string;
  motivation?: string;
  hcaptcha_token?: string;
}

export interface LesmateriaalItem {
  id: number;
  title: string;
  type: string;
  target_age_group: string | null;
  description: string | null;
  lesnummer: number | null;
}

export interface LesmateriaalDetail extends LesmateriaalItem {
  body: string | null;
  metadata: Record<string, unknown> | null;
}

export interface KlasItem {
  id: number;
  naam: string;
  niveau: string | null;
  actief: boolean;
  verloopt_op: string | null;
  les_ids: number[];
  aantal_antwoorden: number;
  aangemaakt_op: string | null;
}

export interface KlasMetCode extends KlasItem {
  code: string;
}

export interface AntwoordItem {
  id: number;
  les_id: number;
  leerling: string;
  antwoorden: Record<string, string>;
  feedback: string | null;
  feedback_op: string | null;
  bijgewerkt_op: string | null;
  verwijderd_na: string | null;
}

export interface LeerlingAntwoord {
  naam: string | null;
  antwoorden: Record<string, string>;
  feedback: string | null;
  bijgewerkt_op: string | null;
  verwijderd_na: string | null;
}

export interface WerkbladVraag {
  sleutel: string;
  sectie: string;
  tekst: string;
}

export interface DocentAanvraagItem {
  id: number;
  name: string;
  email: string;
  school: string;
  function: string | null;
  motivation: string | null;
  status: 'pending' | 'approved' | 'rejected';
  created_at: string | null;
  decided_at: string | null;
}

export interface DocentItem {
  id: number;
  email: string;
  display_name: string | null;
  aantal_klassen: number;
}
