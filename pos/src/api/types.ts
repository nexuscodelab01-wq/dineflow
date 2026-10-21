export type DevicePairResponse = {
  device_id: number;
  label: string;
  device_token: string;
};

// TILL owns a cash drawer (mandatory shift + float); HANDHELD is carried by a server and has none.
export type DeviceKind = 'TILL' | 'HANDHELD';

export type PinLoginResponse = {
  pos_session_token: string;
  staff_name: string;
  device_kind: DeviceKind;
  currency: string;
  country: string;
  tips_enabled: boolean;
  controls_enabled: boolean;
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
  has_modifiers?: boolean;
};

export type MenuModifierOption = { id: number; name: string; price_adjustment: string };
export type MenuModifier = {
  id: number;
  name: string;
  is_required: boolean;
  min_selections: number;
  max_selections: number;
  options: MenuModifierOption[];
};
export type MenuItemDetail = MenuItem & { modifiers: MenuModifier[] };

export type PosCustomer = { id: number; name: string; email: string | null; phone: string | null; points: number; is_vip: boolean };
export type CouponPreview = { code: string; description: string | null; discount: string };

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

export type RestaurantTableRow = {
  table_id: number;
  table_number: string;
  zone: string | null;
  capacity: number;
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
  card_tips: string;
  cash_tips: string;
};

export type CashMovementKind = 'PAID_IN' | 'PAID_OUT';

export type TimeEntryRead = {
  id: number;
  clock_in_at: string;
  clock_out_at: string | null;
  counted_cash: string | null;
  cash_tips: string;
  expected_cash: string;
  variance: string | null;
};

export type ApiErrorBody = {
  detail?: string;
};

export type ControlKind = 'VOID' | 'COMP' | 'DISCOUNT' | 'REFUND';
export type ControlAction = 'void' | 'comp' | 'discount' | 'refund';
export type Reason = { code: string; label: string };
export type Reasons = Record<ControlKind, Reason[]>;

export type AdjustmentResult = { adjustment_id: number; amount: string; order_total: string | null };

export type TabItem = {
  item_id: number | null;
  name: string;
  quantity: number;
  line_total: string;
  discount_amount: string;
  special_instructions: string | null;
  options: string[];
};
export type TabRound = { order_id: number; order_number: string; round_no: number | null; status: string; total: string; items: TabItem[] };
export type TabDetail = { session_id: number; table_number: string; rounds: TabRound[]; total: string };

export type RecentPayment = {
  kind: 'ORDER' | 'TAB';
  id: number;
  label: string;
  amount: string;
  method: string;
  paid_at: string;
  refundable: boolean;
};
