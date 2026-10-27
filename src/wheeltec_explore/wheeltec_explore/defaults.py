"""Single source for explorer engineering defaults; runtime ROS parameters override them."""
DEFAULTS = {
    'map_frame':'map', 'odom_frame':'odom', 'base_frame':'base_link',
    'robot_radius':.35, 'min_frontier_size':.25, 'min_goal_distance':.2,
    'visited_radius':.30, 'observation_min_separation':.30,
    'frontier_approach_radius':.6, 'start_snap_distance':.15,
    'return_tolerance':.15, 'distance_score_bias':.1, 'score_distance_offset':.5,
    'minimum_free_area':8., 'goal_timeout':120., 'task_timeout':900., 'max_goals':60,
    'retry_cooldown':20., 'max_attempts':3, 'retry_radius':.35,
    'map_update_timeout':15., 'scan_max_age':1., 'tf_max_age':1.,
    'future_tolerance':.1, 'slam_transform_timeout':.2,
    'map_jump_translation':.5, 'map_jump_rotation':.35,
    'initialization_timeout':90., 'nav_server_timeout':60.,
    'goal_response_timeout':10., 'cancel_response_timeout':5.,
    'cancel_result_timeout':15., 'map_save_timeout':30.,
    'retry_map_wait':3., 'stable_empty_maps':3,
}
