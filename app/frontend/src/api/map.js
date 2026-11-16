import { req } from './client'

export const mapApi = {
  zones: () => req('/api/zones'),
  metroStations: () => req('/api/metro/stations'),
}
