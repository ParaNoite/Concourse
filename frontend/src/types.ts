export interface ScheduleEvent {
  id: number
  platform: string
  source_id: string
  title: string
  description: string
  location: string
  meeting_url: string | null
  start_at: string | null
  end_at: string | null
  tz_original: string | null
  all_day: boolean
  status: string
  submission_policy: string
  organizer_name: string | null
  organizer_email: string | null
  attendees: any[] | null
  recurrence_rrule: string | null
  content_hash: string
  raw_payload: Record<string, any> | null
  first_seen_at: string
  last_seen_at: string
  updated_at: string
}

export interface StagedEvent {
  id: number
  platform: string
  source_id: string
  title: string
  description: string
  start_at: string | null
  end_at: string | null
  tz_original: string | null
  all_day: boolean
  status: string
  submission_policy: string
  proposed_by: string
  created_at: string
  raw_payload: Record<string, any> | null
}

export interface AddEventPayload {
  message: string
}
