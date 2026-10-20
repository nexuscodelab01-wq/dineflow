export type DevicePairResponse = {
  device_id: number;
  label: string;
  device_token: string;
};

export type PinLoginResponse = {
  pos_session_token: string;
  staff_name: string;
  expires_in: number;
};

export type MenuItem = {
  id: number;
  restaurant_id: number;
  category_id: number;
  category_name: string | null;
  name: string;
  description: string | null;
  price: string; // Decimal, serialized as a string
  image_url: string | null;
  is_available: boolean;
  is_vegetarian: boolean;
  is_spicy: boolean;
  is_popular: boolean;
};

export type MenuListResponse = {
  items: MenuItem[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
};

export type Category = {
  id: number;
  name: string;
  slug: string;
  description: string | null;
  sort_order: number;
  is_active: boolean;
};

export type OpenSession = {
  session_id: number;
  table_id: number;
  table_number: string;
  opened_at: string;
  guests: number;
  rounds: number;
  total: string;
  requests: string[];
};

export type OpenTableSessionsResponse = {
  sessions: OpenSession[];
};

export type PosOrderItem = {
  menu_item_id: number;
  quantity: number;
  modifier_option_ids: number[];
  special_instructions?: string | null;
};

export type PosOrderRead = {
  order_id: number;
  order_number: string;
  total: string;
  status: string;
};

export type PosCardIntentRead = {
  order_id: number;
  status: string;
  client_secret: string | null;
  provider_intent_id?: string | null;
};

export type PosConnectionTokenResponse = {
  secret: string;
};

export type TablePaymentRead = {
  client_secret?: string | null;
  closed?: boolean;
};

export type ShiftRead = {
  shift_id: number;
  state: string;
  opened_at: string;
  opened_by: string | null;
  starting_float: string;
};

export type ShiftReportRead = {
  shift_id: number;
  opened_at: string;
  opened_by: string | null;
  closed_at: string | null;
  closed_by: string | null;
  starting_float: string;
  cash_total: string;
  card_total: string;
  order_count: number;
  expected_cash: string;
  counted_cash: string | null;
  variance: string | null;
};

export type CashMovementKind = 'PAID_IN' | 'PAID_OUT';

export type TimeEntryRead = {
  id: number;
  clock_in_at: string;
  clock_out_at: string | null;
};

export type ApiErrorBody = {
  detail?: string;
};
