package dissect

import (
	"strings"

	"github.com/rs/zerolog/log"
)

func readDefuserTimer(r *Reader) error {
	timer, err := r.String()
	if err != nil {
		return err
	}
	if err = r.Skip(34); err != nil {
		return err
	}
	id, err := r.Bytes(4)
	if err != nil {
		return err
	}
	i := r.PlayerIndexByID(id)
	a := DefuserPlantStart
	if r.planted {
		a = DefuserDisableStart
	}
	if i > -1 {
		u := MatchUpdate{
			Type:          a,
			Username:      r.Header.Players[i].Username,
			Time:          r.timeRaw,
			TimeInSeconds: r.time,
		}
		r.MatchFeedback = append(r.MatchFeedback, u)
		log.Debug().Interface("match_update", u).Send()
		r.lastDefuserPlayerIndex = i
	}
	// TODO: 0.00 can be present even if defuser was not disabled.
	if !strings.HasPrefix(timer, "0.00") {
		return nil
	}
	a = DefuserDisableComplete
	if !r.planted {
		a = DefuserPlantComplete
		r.planted = true
	}
	// Newer replays (seen on Y11S3) no longer carry the player ID in the defuser packet,
	// so the player can be unknown. Leave the username empty rather than guessing.
	username := ""
	if r.lastDefuserPlayerIndex > -1 {
		username = r.Header.Players[r.lastDefuserPlayerIndex].Username
	}
	u := MatchUpdate{
		Type:          a,
		Username:      username,
		Time:          r.timeRaw,
		TimeInSeconds: r.time,
	}
	r.MatchFeedback = append(r.MatchFeedback, u)
	log.Debug().Interface("match_update", u).Send()
	return nil
}
